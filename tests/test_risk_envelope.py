from __future__ import annotations

import unittest
from types import SimpleNamespace

import pandas as pd

from backtest.live_gate import evaluate_preference_live_gate
from backtest.preference import _admission_note, _candidate_baskets
from backtest.risk_envelope import (
    evaluate_incumbent_risk_guard,
    evaluate_target_risk_envelope,
)
from core.config import Symbol


def _candidate(**overrides) -> dict:
    row = {
        "basket": "test_candidate",
        "defense_mode": "static_safe_weight",
        "safe_weight": 0.26,
        "windows": 18,
        "win_rate": 0.72,
        "excess_p10": -0.01,
        "excess_p50": 0.04,
        "excess_p90": 0.09,
        "dd_relief_p10": -0.04,
        "dd_relief_p50": -0.02,
        "dd_relief_p90": 0.01,
        "xirr_p10": 0.10,
        "xirr_p50": 0.20,
        "xirr_p90": 0.29,
        "maxdd_p10": 0.18,
        "maxdd_p50": 0.22,
        "maxdd_p90": 0.25,
    }
    row.update(overrides)
    return row


def _incumbent(**overrides) -> dict:
    row = {
        "available": True,
        "windows": 18,
        "xirr_p10": 0.11,
        "xirr_p50": 0.20,
        "xirr_p90": 0.28,
        "maxdd_p10": 0.17,
        "maxdd_p50": 0.218,
        "maxdd_p90": 0.24,
    }
    row.update(overrides)
    return row


class RiskEnvelopeTests(unittest.TestCase):
    def test_current_config_row_keeps_symbols_outside_the_candidate_pool(self):
        cfg = SimpleNamespace(symbols=[
            Symbol(ticker="NVDA", cap_total=3000),
            Symbol(ticker="MSFT", cap_total=4000),
            Symbol(ticker="TXN", cap_total=5000),
        ])
        metrics = pd.DataFrame([
            {"ticker": "NVDA", "ret_3y": 0.8, "attack_score": 0.9, "vol_3y": 0.5},
            {"ticker": "MSFT", "ret_3y": 0.4, "attack_score": 0.6, "vol_3y": 0.3},
        ]).set_index("ticker", drop=False)

        baskets = _candidate_baskets(
            cfg,
            ["NVDA", "MSFT"],
            {"candidate": ["NVDA", "MSFT"]},
            metrics,
        )
        current = next(item for item in baskets if item.name == "current_config")

        self.assertEqual(current.tickers, ("NVDA", "MSFT", "TXN"))
        self.assertAlmostEqual(sum(dict(current.weights).values()), 1.0)

    def test_controlled_attack_is_inside_explicit_target_budget(self):
        result = evaluate_target_risk_envelope(_candidate(), target="012922")

        self.assertTrue(result["passed"])
        self.assertEqual(result["classification"], "CONTROLLED_ATTACK")
        self.assertAlmostEqual(result["metrics"]["dd_cost_p50"], 0.02)
        self.assertAlmostEqual(result["metrics"]["dd_cost_bad_tail"], 0.04)

    def test_target_bad_tail_exceeding_budget_fails(self):
        result = evaluate_target_risk_envelope(
            _candidate(dd_relief_p10=-0.051), target="012922"
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["classification"], "OUTSIDE_TARGET_ENVELOPE")

    def test_missing_tail_evidence_fails_closed(self):
        row = _candidate()
        row.pop("dd_relief_p10")

        result = evaluate_target_risk_envelope(row, target="012922")

        self.assertFalse(result["available"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["classification"], "INSUFFICIENT_EVIDENCE")

    def test_incumbent_guard_uses_xirr_p10_and_maxdd_p90(self):
        passing = evaluate_incumbent_risk_guard(_candidate(), _incumbent())
        tail_failure = evaluate_incumbent_risk_guard(
            _candidate(xirr_p10=0.08, maxdd_p90=0.27), _incumbent()
        )

        self.assertTrue(passing["passed"])
        self.assertFalse(tail_failure["passed"])
        failed = {item["name"] for item in tail_failure["checks"] if not item["passed"]}
        self.assertIn("xirr_margin_p10_vs_incumbent", failed)
        self.assertIn("dd_cost_p90_vs_incumbent", failed)

    def test_incumbent_guard_pairs_the_same_rolling_starts_before_quantiles(self):
        candidate = _candidate(rolling_samples=[
            {"start": "2022-01-01", "xirr": 0.49, "maxdd": 0.39},
            {"start": "2022-02-01", "xirr": 0.10, "maxdd": 0.21},
        ])
        incumbent = _incumbent(rolling_samples=[
            {"start": "2022-01-01", "xirr": 0.10, "maxdd": 0.20},
            {"start": "2022-02-01", "xirr": 0.50, "maxdd": 0.40},
        ])

        result = evaluate_incumbent_risk_guard(
            candidate,
            incumbent,
            policy={"min_rolling_windows": 2},
        )

        self.assertEqual(result["comparison_basis"], "paired_rolling_start_deltas")
        self.assertEqual(result["paired_evidence"]["windows"], 2)
        self.assertFalse(result["passed"])
        self.assertLess(result["margins"]["xirr_p10_vs_incumbent"], -0.02)
        self.assertGreater(result["margins"]["dd_cost_p90_vs_incumbent"], 0.02)

    def test_preference_admission_labels_dd_tradeoff(self):
        admission = _admission_note(_candidate(), "012922")

        self.assertEqual(admission["stage"], "eligible")
        self.assertEqual(admission["label"], "风险包络内候选")
        self.assertEqual(
            admission["risk_envelope"]["classification"], "CONTROLLED_ATTACK"
        )

    def test_live_gate_requires_both_target_and_incumbent_envelopes(self):
        row = _candidate(
            tickers=["NVDA", "MSFT"],
            weights={"NVDA": 0.5, "MSFT": 0.5},
            n=2,
        )
        row["admission"] = _admission_note(row, "012922")
        research = {
            "summary": {
                "target_benchmark": "012922",
                "total_cap": 10000,
                "incumbent_guard": _incumbent(),
            },
            "rows": [row],
        }

        gate = evaluate_preference_live_gate(research)

        self.assertEqual(gate["decision"], "RESEARCH_CANDIDATE_ONLY")
        self.assertTrue(gate["risk_envelope"]["passed"])
        self.assertFalse(gate["live_connected"])
        self.assertFalse(gate["does_change_today_advice"])


if __name__ == "__main__":
    unittest.main()
