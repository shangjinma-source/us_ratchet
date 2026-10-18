from __future__ import annotations

import copy
import unittest
from pathlib import Path

import yaml

from backtest.ndx_marginal_allocation import (
    NdxMarginalAllocationError,
    allocate_new_money,
    build_plan_rows,
    current_incumbent_snapshot,
    load_plan,
    portfolio_shape,
    validate_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxMarginalAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load(
            (ROOT / "config" / "config.yaml").read_text(encoding="utf-8")
        )
        cls.spec_path = ROOT / "config" / "ndx_marginal_allocation_v11_plan.yaml"
        cls.spec_raw = yaml.safe_load(cls.spec_path.read_text(encoding="utf-8"))

    def test_current_snapshot_matches_eight_name_incumbent(self):
        snapshot = current_incumbent_snapshot(self.config)

        self.assertEqual(
            snapshot["tickers"],
            ["NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG"],
        )
        self.assertEqual(snapshot["holding_count"], 8)
        self.assertAlmostEqual(snapshot["safe_weight"], 0.26)
        self.assertGreater(snapshot["effective_n"], 7.0)
        self.assertLess(snapshot["effective_n"], 8.0)
        self.assertNotIn("QQQ", snapshot["weights"])

    def test_new_money_allocation_never_sells_existing_holdings(self):
        allocation = allocate_new_money(
            1000.0,
            {"A": 0.5, "B": 0.3, "C": 0.2},
            candidate_share=0.10,
            candidate_weights={"D": 1.0},
        )

        self.assertAlmostEqual(float(allocation["allocation"].sum()), 1000.0)
        self.assertAlmostEqual(
            float(allocation.loc[allocation["ticker"].eq("D"), "allocation"].sum()),
            100.0,
        )
        self.assertAlmostEqual(
            float(
                allocation.loc[
                    allocation["role"].eq("incumbent"), "allocation"
                ].sum()
            ),
            900.0,
        )
        self.assertEqual(
            float(allocation["existing_holding_sell_notional"].sum()), 0.0
        )

    def test_candidate_constraints_fail_closed(self):
        with self.assertRaisesRegex(NdxMarginalAllocationError, "QQQ"):
            allocate_new_money(
                1000.0,
                {"A": 1.0},
                candidate_share=0.10,
                candidate_weights={"QQQ": 1.0},
            )

        with self.assertRaises(NdxMarginalAllocationError):
            portfolio_shape({"A": 0.9, "B": 0.2})

    def test_registered_plan_rejects_ordinary_topn_grid(self):
        invalid = copy.deepcopy(self.spec_raw)
        invalid["stage_1_marginal"]["top_ns"] = [6, 8, 10, 12]

        with self.assertRaisesRegex(NdxMarginalAllocationError, "ordinary parameter grids"):
            validate_plan(invalid, config=self.config)

    def test_registered_plan_does_not_guess_unclassified_risk_chains(self):
        invalid = copy.deepcopy(self.spec_raw)
        del invalid["stage_1_marginal"]["candidate_selection"]["taxonomy_gate"]

        with self.assertRaisesRegex(NdxMarginalAllocationError, "accepted taxonomy"):
            validate_plan(invalid, config=self.config)

    def test_registered_plan_expands_marginal_stage_before_disabled_whole_sleeve(self):
        spec = load_plan(self.spec_path, config=self.config)
        audit = spec["_audit"]
        self.assertTrue(audit["passed"])
        self.assertFalse(audit["old_holding_sale_allowed"])
        self.assertEqual(audit["candidate_share_of_new_money"], [0.0, 0.05, 0.10, 0.15])

        rows = build_plan_rows(spec, config=self.config)
        self.assertEqual(len(rows), 8)
        self.assertEqual(int(rows["enabled"].sum()), 4)
        self.assertEqual(
            set(rows.loc[rows["enabled"], "projected_holding_count"]),
            {8, 9},
        )
        self.assertEqual(
            set(rows.loc[~rows["enabled"], "projected_holding_count"]),
            {6, 8, 10, 12},
        )
        self.assertTrue(rows.loc[~rows["enabled"], "old_holding_sell_allowed"].all())


if __name__ == "__main__":
    unittest.main()
