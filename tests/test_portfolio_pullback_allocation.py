from __future__ import annotations

import unittest
from pathlib import Path

from backtest.portfolio_pullback_allocation import (
    PortfolioPullbackAllocationError,
    allocate_whole_lots,
    parse_weight_map,
    risk_chain_shape,
)
from scripts.portfolio_pullback_pooled_reserve_audit import _candidate_tables


ROOT = Path(__file__).resolve().parents[1]


class PortfolioPullbackAllocationTests(unittest.TestCase):
    def test_exact_whole_lot_search_is_deterministic_and_self_funding(self):
        result = allocate_whole_lots(
            450.0,
            "AAA:0.5;BBB:0.5",
            {"AAA": 100.0, "BBB": 200.0},
            fee_bps=10.0,
        )
        self.assertEqual(result.shares, {"AAA": 2, "BBB": 1})
        self.assertLessEqual(sum(result.notionals.values()) + result.fees_usd, 450.0)
        self.assertGreater(result.deployment_ratio, 0.88)
        self.assertAlmostEqual(result.effective_n, 2.0)

    def test_sub_lot_budget_remains_cash_and_never_fabricates_fractional_share(self):
        result = allocate_whole_lots(99.0, {"AAA": 1.0}, {"AAA": 100.0})
        self.assertEqual(result.shares, {})
        self.assertEqual(result.deployment_ratio, 0.0)
        self.assertEqual(result.residual_cash_usd, 99.0)

    def test_weights_and_risk_chains_fail_closed(self):
        self.assertEqual(parse_weight_map("BBB:1;AAA:1"), {"AAA": 0.5, "BBB": 0.5})
        self.assertEqual(risk_chain_shape({"AAA": 100, "BBB": 100}, {"AAA": "x", "BBB": "x"}), (1.0, 1.0))
        with self.assertRaises(PortfolioPullbackAllocationError):
            allocate_whole_lots(100.0, {"AAA": 1.0}, {"AAA": 0.0})

    def test_registry_loader_excludes_migration_controls(self):
        active, risk_maps = _candidate_tables(
            ROOT / "data/cache/research/ndx_challenger_forward_registry_v3/active_forward_registry.csv",
            ROOT / "data/cache/research/ndx_challenger_master_table_v1/challenger_master_table.csv",
            ROOT / "data/cache/research/ndx_challenger_forward_registry_v3/frozen_candidate_risk_chain_map.csv",
        )
        self.assertEqual(len(active), 4)
        self.assertTrue(active["research_track"].eq("portfolio_optimization").all())
        self.assertTrue(active["action_scope_registry"].eq("VARIABLE_CARDINALITY").all())
        self.assertEqual(set(active["holding_count"]), {4, 6})
        self.assertEqual(set(risk_maps), set(active["candidate_id"]))


if __name__ == "__main__":
    unittest.main()
