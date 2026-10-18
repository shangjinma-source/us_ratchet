from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backtest.weights import (
    WeightConstraintError,
    bounded_proportional_weights,
    project_concentration_envelope_weights,
)


class WeightConstraintTests(unittest.TestCase):
    def test_extreme_concentration_respects_hard_cap_and_floor(self):
        raw = pd.Series({"A": 0.999, "B": 0.0005, "C": 0.0003, "D": 0.0002})

        weights = bounded_proportional_weights(
            raw, max_weight=0.30, min_weight=0.02
        )

        self.assertAlmostEqual(float(weights.sum()), 1.0, places=12)
        self.assertLessEqual(float(weights.max()), 0.30 + 1e-12)
        self.assertGreaterEqual(float(weights.min()), 0.02 - 1e-12)

    def test_infeasible_user_cap_uses_equal_weight_as_effective_cap(self):
        raw = pd.Series({"A": 9.0, "B": 1.0, "C": 1.0, "D": 1.0})

        weights = bounded_proportional_weights(
            raw, max_weight=0.20, min_weight=0.02
        )

        np.testing.assert_allclose(weights.to_numpy(), np.repeat(0.25, 4), atol=1e-12)

    def test_floor_and_cap_produce_the_exact_feasible_solution(self):
        raw = pd.Series({"A": 8.0, "B": 4.0, "C": 1.0, "D": 0.01})

        weights = bounded_proportional_weights(
            raw, max_weight=0.50, min_weight=0.10
        )

        self.assertAlmostEqual(weights["A"], 0.50, places=12)
        self.assertAlmostEqual(weights["B"], 0.30, places=12)
        self.assertAlmostEqual(weights["C"], 0.10, places=12)
        self.assertAlmostEqual(weights["D"], 0.10, places=12)
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=12)

    def test_non_finite_raw_weight_fails_closed(self):
        with self.assertRaisesRegex(WeightConstraintError, "finite"):
            bounded_proportional_weights(
                pd.Series({"A": 1.0, "B": np.nan}),
                max_weight=0.60,
                min_weight=0.0,
            )

    def test_envelope_projection_preserves_asymmetry_inside_top_three_cap(self):
        raw = pd.Series(
            {
                "A": 0.25,
                "B": 0.21,
                "C": 0.17,
                "D": 0.10,
                "E": 0.08,
                "F": 0.07,
                "G": 0.05,
                "H": 0.04,
                "I": 0.02,
                "J": 0.01,
            }
        )

        weights = project_concentration_envelope_weights(
            raw,
            max_weight=0.18,
            min_weight=0.0,
            top_weight_count=3,
            top_weight_cap=0.45,
        )

        self.assertAlmostEqual(float(weights.sum()), 1.0, places=9)
        self.assertLessEqual(float(weights.max()), 0.18 + 1e-9)
        self.assertLessEqual(
            float(weights.nlargest(3).sum()),
            0.45 + 1e-9,
        )
        self.assertGreater(weights["A"], weights["B"] + 1e-3)
        self.assertGreater(weights["B"], weights["C"] + 1e-3)
        uniform_cap = bounded_proportional_weights(
            raw,
            max_weight=0.15,
            min_weight=0.0,
        )
        target = raw / float(raw.sum())
        projected_error = float(np.square(weights - target).sum())
        uniform_cap_error = float(np.square(uniform_cap - target).sum())
        self.assertLess(projected_error, uniform_cap_error)

    def test_envelope_projection_respects_effective_name_floor(self):
        raw = pd.Series({chr(65 + index): 10.0 ** -index for index in range(8)})

        weights = project_concentration_envelope_weights(
            raw,
            max_weight=0.20,
            min_weight=0.0,
            top_weight_count=3,
            top_weight_cap=0.50,
            min_effective_n=7.0,
        )

        effective_n = 1.0 / float(np.square(weights).sum())
        self.assertGreaterEqual(effective_n, 7.0 - 1e-8)
        self.assertLessEqual(float(weights.nlargest(3).sum()), 0.50 + 1e-9)

    def test_envelope_projection_rejects_infeasible_top_group_cap(self):
        raw = pd.Series({chr(65 + index): 1.0 for index in range(8)})

        with self.assertRaisesRegex(WeightConstraintError, "feasible"):
            project_concentration_envelope_weights(
                raw,
                max_weight=0.20,
                min_weight=0.0,
                top_weight_count=3,
                top_weight_cap=0.35,
            )

    def test_envelope_projection_is_deterministic(self):
        raw = pd.Series({chr(65 + index): 9.0 - index for index in range(8)})
        kwargs = {
            "max_weight": 0.18,
            "min_weight": 0.0,
            "top_weight_count": 3,
            "top_weight_cap": 0.45,
            "min_effective_n": 7.0,
        }

        first = project_concentration_envelope_weights(raw, **kwargs)
        second = project_concentration_envelope_weights(raw, **kwargs)

        np.testing.assert_allclose(first.to_numpy(), second.to_numpy(), atol=1e-12)

    def test_envelope_projection_respects_independent_risk_group_cap(self):
        raw = pd.Series({"A": 0.50, "B": 0.30, "C": 0.15, "D": 0.05})
        weights = project_concentration_envelope_weights(
            raw,
            max_weight=0.45,
            min_weight=0.05,
            top_weight_count=3,
            top_weight_cap=0.85,
            group_labels={"A": "compute", "B": "compute", "C": "software", "D": "network"},
            max_group_weight=0.55,
        )
        self.assertLessEqual(float(weights[["A", "B"]].sum()), 0.55 + 1e-9)
        self.assertLessEqual(float(weights.nlargest(3).sum()), 0.85 + 1e-9)

    def test_envelope_projection_fails_when_risk_group_cap_is_infeasible(self):
        raw = pd.Series({"A": 0.6, "B": 0.4})
        with self.assertRaisesRegex(WeightConstraintError, "projection failed"):
            project_concentration_envelope_weights(
                raw,
                max_weight=0.70,
                min_weight=0.0,
                top_weight_count=1,
                top_weight_cap=0.70,
                group_labels={"A": "compute", "B": "compute"},
                max_group_weight=0.55,
            )


if __name__ == "__main__":
    unittest.main()
