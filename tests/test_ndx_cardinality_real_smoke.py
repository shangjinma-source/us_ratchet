from __future__ import annotations

import unittest

import pandas as pd

from scripts.ndx_cardinality_real_smoke import (
    NdxCardinalityRealSmokeError,
    _assign_replay_frontiers,
    _attach_point_in_time_identity_columns,
)


def _row(
    portfolio_id: str,
    holding_count: int,
    return_p50: float,
    return_p10: float,
    drawdown: float,
    distance: float,
    turnover: float,
    compliant: bool = True,
) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "holding_count": holding_count,
        "return_p50": return_p50,
        "return_p10": return_p10,
        "max_drawdown_p50": drawdown,
        "max_drawdown_p90": drawdown,
        "target_012922_distance": distance,
        "turnover": turnover,
        "declared_constraints_passed": compliant,
    }


class CardinalityRealSmokeReplayFrontierTests(unittest.TestCase):
    def test_tags_within_k_and_across_dynamic_cardinality(self):
        frame = pd.DataFrame([
            _row("k2-return", 2, 0.20, 0.05, 0.25, 0.30, 0.10),
            _row("k2-risk", 2, 0.10, 0.04, 0.10, 0.20, 0.10),
            _row("k3-dominant", 3, 0.30, 0.08, 0.08, 0.05, 0.05),
            _row("k3-failed", 3, 0.40, 0.10, 0.07, 0.04, 0.04, False),
        ])

        tagged = _assign_replay_frontiers(frame).set_index("portfolio_id")

        self.assertIn("RETURN", tagged.loc["k2-return", "frontier_tags"])
        self.assertIn("DRAWDOWN", tagged.loc["k2-risk", "frontier_tags"])
        self.assertEqual(
            tagged.loc["k2-return", "cross_cardinality_frontier_tags"], ""
        )
        self.assertIn(
            "PARETO", tagged.loc["k3-failed", "cross_cardinality_frontier_tags"]
        )
        self.assertEqual(
            tagged.loc["k3-failed", "cross_cardinality_constrained_frontier_tags"], ""
        )
        self.assertIn(
            "RETURN",
            tagged.loc["k3-dominant", "cross_cardinality_constrained_frontier_tags"],
        )

    def test_rejects_empty_input(self):
        with self.assertRaisesRegex(ValueError, "frontier input is incomplete"):
            _assign_replay_frontiers(pd.DataFrame())

    def test_attaches_aligned_point_in_time_security_identities(self):
        candidates = pd.DataFrame([{"tickers": "A;B"}])
        universe = pd.DataFrame([
            {"ticker": "A", "security_id": "security:a", "issuer_id": "issuer:a", "risk_chain": "compute"},
            {"ticker": "B", "security_id": "security:b", "issuer_id": "issuer:b", "risk_chain": "eda_ip"},
        ])
        result = _attach_point_in_time_identity_columns(candidates, universe)
        self.assertEqual(result.loc[0, "security_ids"], "security:a;security:b")
        self.assertEqual(result.loc[0, "issuer_ids"], "issuer:a;issuer:b")
        self.assertEqual(result.loc[0, "risk_chains"], "compute;eda_ip")

    def test_rejects_two_share_classes_from_one_issuer(self):
        candidates = pd.DataFrame([{"tickers": "A;A2"}])
        universe = pd.DataFrame([
            {"ticker": "A", "security_id": "security:a", "issuer_id": "issuer:a", "risk_chain": "compute"},
            {"ticker": "A2", "security_id": "security:a2", "issuer_id": "issuer:a", "risk_chain": "compute"},
        ])
        with self.assertRaisesRegex(NdxCardinalityRealSmokeError, "issuer uniqueness"):
            _attach_point_in_time_identity_columns(candidates, universe)


if __name__ == "__main__":
    unittest.main()
