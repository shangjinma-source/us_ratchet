from __future__ import annotations

import unittest

from backtest.ndx_cardinality_beam_convergence import audit_beam_width_convergence
from backtest.ndx_cardinality_discovery import NdxCardinalityDiscoveryError, synthetic_fixture


class CardinalityBeamConvergenceTests(unittest.TestCase):
    def test_max_width_converges_to_exact_fixture(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=7, business_days=180)
        frame, audit = audit_beam_width_convergence(
            universe,
            returns,
            target,
            incumbent,
            holding_count=3,
            beam_widths=[1, 2, 4, 8, 16],
            search_kwargs={
                "window_days": 42,
                "step_days": 21,
                "fit_days": 63,
                "transaction_cost_bps": 10.0,
                "weight_specs": ("equal_weight",),
            },
        )
        final = frame.iloc[-1]
        self.assertTrue(bool(final["candidate_set_equals_exact"]))
        self.assertTrue(bool(final["all_four_objective_winners_recalled"]))
        self.assertEqual(float(final["candidate_set_recall"]), 1.0)
        self.assertFalse(bool(final["mathematical_bound_certificate_available"]))
        self.assertFalse(audit["promotion_allowed"])

    def test_widths_must_be_unique_and_ascending(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=7, business_days=180)
        with self.assertRaisesRegex(NdxCardinalityDiscoveryError, "positive, unique, and ascending"):
            audit_beam_width_convergence(
                universe,
                returns,
                target,
                incumbent,
                holding_count=3,
                beam_widths=[2, 1, 2],
                search_kwargs={
                    "window_days": 42,
                    "step_days": 21,
                    "fit_days": 63,
                    "transaction_cost_bps": 10.0,
                },
            )


if __name__ == "__main__":
    unittest.main()
