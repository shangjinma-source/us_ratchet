import copy
import math
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_cardinality_search import (
    NdxCardinalitySearchError,
    build_search_universe,
    cardinality_space,
    issuer_dedup_combination_counts,
    load_search_plan,
    validate_search_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxCardinalitySearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = load_search_plan(ROOT / "config" / "ndx_cardinality_search_v1_plan.yaml")

    def test_plan_keeps_count_dynamic_and_012922_core(self):
        audit = validate_search_plan(self.plan)
        self.assertTrue(audit["passed"])
        self.assertEqual(
            self.plan["objective_contract"]["holding_count_policy"],
            "dynamic_from_one_to_eligible_issuer_count",
        )
        self.assertEqual(
            self.plan["objective_contract"]["target_012922_role"],
            "core_return_drawdown_envelope",
        )
        self.assertEqual(
            self.plan["objective_contract"]["portfolio_scope"],
            "hsbc_us_equity_sleeve_only",
        )
        self.assertEqual(
            self.plan["objective_contract"]["safe_leg_role"],
            "excluded_from_optimization_and_comparison",
        )

    def test_safe_leg_cannot_reenter_stock_sleeve_research(self):
        changed = copy.deepcopy(self.plan)
        changed["objective_contract"]["safe_leg_role"] = "included"
        with self.assertRaises(NdxCardinalitySearchError):
            validate_search_plan(changed)

    def test_fixed_holding_count_plan_is_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed["objective_contract"]["holding_count_policy"] = [6, 8, 10, 12]
        with self.assertRaises(NdxCardinalitySearchError):
            validate_search_plan(changed)

    def test_issuer_dedup_counts_multiple_share_classes(self):
        self.assertEqual(issuer_dedup_combination_counts([2, 1]), [1, 3, 2])

    def test_cardinality_covers_one_to_unique_issuer_count(self):
        universe = pd.DataFrame([
            {"security_id": "a", "issuer_id": "i1", "strict_technology_eligible": True, "technology_plus_adjacent_eligible": True},
            {"security_id": "b", "issuer_id": "i1", "strict_technology_eligible": True, "technology_plus_adjacent_eligible": True},
            {"security_id": "c", "issuer_id": "i2", "strict_technology_eligible": True, "technology_plus_adjacent_eligible": True},
        ])
        result = cardinality_space(universe, track="strict_technology", exact_limit=10)
        self.assertEqual(result["holding_count"].tolist(), [1, 2])
        self.assertEqual(result["issuer_dedup_feasible_combinations"].tolist(), ["3", "2"])


if __name__ == "__main__":
    unittest.main()
