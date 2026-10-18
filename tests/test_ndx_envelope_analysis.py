from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd

from backtest.ndx_envelope_analysis import (
    paired_profile_effects,
    profile_equivalence_audit,
    stage5_composition_ablation_spec,
)


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class NdxEnvelopeAnalysisTests(unittest.TestCase):
    def test_paired_effects_keep_cost_and_window_attribution_exact(self):
        candidates = pd.DataFrame([
            {
                "profile_id": profile,
                "lookback_years": 3.0,
                "trade_cost_bps": cost,
                "incumbent_win_rate": win,
                "incumbent_xirr_p50_margin": p50,
                "incumbent_xirr_p10_margin": p10,
                "incumbent_dd_relief_p50": dd50,
                "incumbent_dd_relief_p90": dd90,
                "turnover_x_p50": turnover,
            }
            for cost in (5.0, 10.0)
            for profile, win, p50, p10, dd50, dd90, turnover in (
                ("baseline", 0.1, -0.08, -0.13, 0.025, 0.008, 5.0),
                ("challenger", 0.3, -0.06, -0.10, 0.020, 0.004, 5.1),
            )
        ])
        windows = pd.DataFrame([
            {
                "profile_id": profile,
                "lookback_years": 3.0,
                "trade_cost_bps": cost,
                "start": start,
                "incumbent_xirr_margin": margin,
                "incumbent_dd_relief": relief,
                "strategy_xirr": 0.3 + margin,
                "strategy_maxdd": 0.2 - relief,
                "turnover_x": 5.0,
            }
            for cost in (5.0, 10.0)
            for start in ("2022-01-11", "2022-02-01")
            for profile, margin, relief in (
                ("baseline", -0.08, 0.02),
                ("challenger", -0.05, 0.01),
            )
        ])

        candidate_effects, window_effects, summary = paired_profile_effects(
            candidates,
            windows,
            challenger_id="challenger",
            baseline_id="baseline",
        )

        self.assertEqual(len(candidate_effects), 2)
        self.assertEqual(len(window_effects), 4)
        self.assertEqual(summary["candidate_p50_return_improvement_count"], 2)
        self.assertEqual(summary["candidate_dd_p90_improvement_count"], 0)
        self.assertEqual(summary["window_return_improvement_rate"], 1.0)
        self.assertEqual(summary["window_dd_improvement_rate"], 0.0)

    def test_equivalence_audit_accepts_only_differences_inside_tolerance(self):
        candidates = pd.DataFrame([
            {
                "profile_id": profile,
                "lookback_years": 3.0,
                "trade_cost_bps": 10.0,
                "incumbent_win_rate": 0.2,
                "incumbent_xirr_p50_margin": -0.05 + adjustment,
                "incumbent_xirr_p10_margin": -0.10,
                "incumbent_dd_relief_p50": 0.02,
                "incumbent_dd_relief_p90": 0.01,
                "turnover_x_p50": 5.0,
            }
            for profile, adjustment in (("left", 0.0), ("right", 5e-9))
        ])
        windows = pd.DataFrame([
            {
                "profile_id": profile,
                "lookback_years": 3.0,
                "trade_cost_bps": 10.0,
                "start": "2022-01-11",
                "incumbent_xirr_margin": -0.05,
                "incumbent_dd_relief": 0.02,
                "strategy_xirr": 0.30,
                "strategy_maxdd": 0.20,
                "turnover_x": 5.0,
            }
            for profile in ("left", "right")
        ])
        selections = pd.DataFrame([
            {
                "profile_id": profile,
                "lookback_years": 3.0,
                "trade_cost_bps": 10.0,
                "window_start": "2022-01-11",
                "selection_date": "2022-01-11",
                "trigger": "scheduled",
                "observed_max_weight": 0.16,
                "observed_top_weight": 0.44,
                "observed_effective_n": 9.5,
            }
            for profile in ("left", "right")
        ])

        result = profile_equivalence_audit(
            candidates,
            windows,
            selections,
            left_id="left",
            right_id="right",
        )

        self.assertTrue(result["economically_equivalent"])
        candidates.loc[candidates["profile_id"].eq("right"), "turnover_x_p50"] = 5.1
        failed = profile_equivalence_audit(
            candidates,
            windows,
            selections,
            left_id="left",
            right_id="right",
        )
        self.assertFalse(failed["economically_equivalent"])

    def test_stage5_contains_baseline_and_every_single_pool24_exclusion(self):
        root = TEST_TMP_ROOT / f"envelope_{uuid.uuid4().hex}"
        root.mkdir(parents=True)
        try:
            manifest = root / "manifest.json"
            shortlist = root / "shortlist.csv"
            manifest.write_text("{}\n", encoding="utf-8")
            shortlist.write_text("shortlist_id,rank,ticker,sic2\n", encoding="utf-8")
            pool24 = pd.DataFrame([
                {
                    "shortlist_id": "pool24",
                    "rank": index + 1,
                    "ticker": f"T{index:02d}",
                    "sic2": index // 2,
                }
                for index in range(24)
            ])
            contract = {
                "incumbent_top1": 0.16425389755011136,
                "incumbent_top3": 0.44265033407572385,
            }

            spec = stage5_composition_ablation_spec(
                source_manifest_path=manifest,
                shortlist_path=shortlist,
                pool24=pool24,
                contract=contract,
                baseline_profile_id="baseline",
            )

            profiles = spec["phases"][0]["construction_profiles"]
            self.assertEqual(len(profiles), 25)
            self.assertEqual(len(profiles[0]["candidate_tickers"]), 24)
            self.assertTrue(
                all(len(profile["candidate_tickers"]) == 23 for profile in profiles[1:])
            )
            omitted = {
                next(iter(set(profiles[0]["candidate_tickers"]) - set(profile["candidate_tickers"])))
                for profile in profiles[1:]
            }
            self.assertEqual(len(omitted), 24)
            self.assertEqual(
                spec["analysis_contract"]["multiple_testing_policy"],
                "screen_only_no_promotion",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
