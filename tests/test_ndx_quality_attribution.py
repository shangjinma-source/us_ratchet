from __future__ import annotations

import unittest

import pandas as pd

from backtest.ndx_quality import QUALITY_POLICY_ID
from backtest.ndx_quality_attribution import (
    NdxQualityAttributionError,
    QUALITY_COLUMNS,
    _verify_selection_cost_invariance,
    build_factor_associations,
    build_replacement_evidence,
    build_selection_evidence,
    build_start_year_summary,
    build_window_attribution,
    build_window_features,
)


def _quality_rows() -> pd.DataFrame:
    rows = []
    values = {"A": 0.5, "B": 0.2, "C": 0.8}
    for date in ("2024-01-02", "2024-02-01"):
        for index, ticker in enumerate(("A", "B", "C")):
            row = {
                "selection_date": date,
                "ticker": ticker,
                "quality_policy_id": QUALITY_POLICY_ID,
                "quality_eligible": True,
                "quality_confidence": "high",
                "sic": 7372 if ticker in {"A", "B"} else 3674,
                "sic_group_2d": "73" if ticker in {"A", "B"} else "36",
                "sic_description": "test",
            }
            for column in QUALITY_COLUMNS:
                row[column] = values[ticker]
            row["quality_score"] = values[ticker] * 100.0
            rows.append(row)
    return pd.DataFrame(rows)


def _selections(*, include_extra_alt_date: bool = False) -> pd.DataFrame:
    rows = [
        {
            "phase_id": "training",
            "job_id": "job-10",
            "window_start": "2024-01-02",
            "profile_id": "seed",
            "selection_date": "2024-01-02",
            "trigger": "scheduled",
            "tickers": "A;B",
            "weights": "A:0.50000000;B:0.50000000",
        },
        {
            "phase_id": "training",
            "job_id": "job-10",
            "window_start": "2024-01-02",
            "profile_id": "quality",
            "selection_date": "2024-01-02",
            "trigger": "scheduled",
            "tickers": "A;C",
            "weights": "A:0.50000000;C:0.50000000",
        },
    ]
    if include_extra_alt_date:
        rows.append({
            "phase_id": "training",
            "job_id": "job-10",
            "window_start": "2024-01-02",
            "profile_id": "quality",
            "selection_date": "2024-02-01",
            "trigger": "stale_holding",
            "tickers": "A;C",
            "weights": "A:0.40000000;C:0.60000000",
        })
    return pd.DataFrame(rows)


class NdxQualityAttributionTests(unittest.TestCase):
    def test_selection_cost_invariance_fails_when_holdings_change(self):
        baseline = _selections().iloc[[0]].copy()
        baseline["trade_cost_bps"] = 10.0
        changed = baseline.copy()
        changed["trade_cost_bps"] = 25.0
        changed["weights"] = "A:0.60000000;B:0.40000000"
        selections = pd.concat([baseline, changed], ignore_index=True)

        with self.assertRaisesRegex(
            NdxQualityAttributionError, "changed across trade costs"
        ):
            _verify_selection_cost_invariance(selections, 10.0)

    def test_selection_evidence_uses_actual_weights_and_point_in_time_quality(self):
        states, holdings = build_selection_evidence(
            _selections(), _quality_rows()
        )

        quality = states.set_index("profile_id").loc["quality"]
        self.assertAlmostEqual(quality["weighted_growth_sleeve"], 0.65)
        self.assertAlmostEqual(quality["weighted_quality_score"], 65.0)
        self.assertAlmostEqual(quality["max_sic4_weight"], 0.5)
        self.assertEqual(len(holdings), 4)

    def test_replacement_evidence_does_not_invent_ticker_pairing(self):
        selections = _selections(include_extra_alt_date=True)
        states, _ = build_selection_evidence(selections, _quality_rows())

        events, tickers, mismatches = build_replacement_evidence(
            selections,
            states,
            _quality_rows(),
            baseline_profile_id="seed",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0]["entered_tickers"], "C")
        self.assertEqual(events.iloc[0]["exited_tickers"], "B")
        self.assertAlmostEqual(
            events.iloc[0]["entered_minus_exited_growth_sleeve"], 0.6
        )
        self.assertEqual(set(tickers["role"]), {"entered", "exited"})
        self.assertNotIn("paired_ticker", tickers.columns)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches.iloc[0]["present_side"], "alternative_only")

    def test_window_attribution_is_paired_and_associations_are_non_causal(self):
        selections = _selections()
        states, _ = build_selection_evidence(selections, _quality_rows())
        windows = pd.DataFrame([
            {
                "phase_id": "training",
                "job_id": "job-10",
                "start": "2024-01-02",
                "end": "2024-03-29",
                "profile_id": profile,
                "lookback_years": 1.0,
                "trade_cost_bps": 10.0,
                "strategy_xirr": xirr,
                "strategy_maxdd": 0.20,
                "target_excess_xirr": xirr - 0.10,
                "target_dd_relief": -0.01,
                "incumbent_xirr_margin": xirr - 0.12,
                "incumbent_dd_relief": -0.02,
                "turnover_x": 1.0,
            }
            for profile, xirr in (("seed", 0.20), ("quality", 0.25))
        ])
        features = build_window_features(windows, states)
        events, _, mismatches = build_replacement_evidence(
            selections,
            states,
            _quality_rows(),
            baseline_profile_id="seed",
        )

        paired = build_window_attribution(
            features,
            events,
            mismatches,
            baseline_profile_id="seed",
        )
        associations = build_factor_associations(paired)
        years = build_start_year_summary(paired)

        self.assertEqual(len(paired), 1)
        self.assertAlmostEqual(paired.iloc[0]["target_excess_xirr_delta"], 0.05)
        self.assertEqual(paired.iloc[0]["replacement_selection_dates"], 1)
        self.assertTrue(bool(associations["overlapping_windows"].all()))
        self.assertFalse(bool(associations["statistical_inference_allowed"].any()))
        self.assertEqual(years.iloc[0]["window_start_year"], 2024)
        self.assertEqual(years.iloc[0]["paired_windows"], 1)


if __name__ == "__main__":
    unittest.main()
