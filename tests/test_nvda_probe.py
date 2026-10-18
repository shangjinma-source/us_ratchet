from __future__ import annotations

import copy
import unittest
from pathlib import Path

from backtest.nvda_probe import NvdaProbePlanError, load_probe_plan, validate_probe_plan
from core.config import load_config
from core.persist import load_portfolio


ROOT = Path(__file__).resolve().parents[1]


class NvdaProbePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config(ROOT / "config" / "config.yaml")
        cls.state = load_portfolio(ROOT / "data" / "state.json")
        cls.plan, cls.audit = load_probe_plan(
            ROOT / "config" / "nvda_probe_layer_v1_plan.yaml",
            cfg=cls.cfg,
            state=cls.state,
        )

    def test_plan_is_one_lot_external_money_and_forward_only(self):
        self.assertTrue(self.audit["passed"])
        self.assertEqual(self.plan["probe_arm"]["fixed_order_lots"], 1)
        self.assertEqual(self.plan["probe_arm"]["budget_source"], "external_new_money_only")
        self.assertFalse(self.plan["evaluation"]["promotion_before_fresh_oos_allowed"])
        self.assertAlmostEqual(self.audit["single_order_notional_cap"], 224.36, places=2)

    def test_parameter_drift_fails_closed(self):
        changed = copy.deepcopy(self.plan)
        changed["probe_arm"]["cooldown_trading_days"] = 19
        with self.assertRaises(NvdaProbePlanError):
            validate_probe_plan(changed, cfg=self.cfg, state=self.state)

    def test_risk_caps_are_bounded_by_one_registered_lot(self):
        self.assertLessEqual(self.audit["maximum_post_probe_nvda_weight"], self.audit["incumbent_top1"])
        self.assertGreater(
            self.audit["maximum_post_probe_semiconductor_chain_weight"],
            self.audit["incumbent_semiconductor_chain_weight"],
        )


if __name__ == "__main__":
    unittest.main()
