from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd
import yaml

from backtest.ndx_marginal_stage1 import allocation_rows, attach_current_competition, build_candidate_readiness, load_current_inputs


ROOT = Path(__file__).resolve().parents[1]


class NdxMarginalStage1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
        cls.frame, cls.versions = load_current_inputs(
            ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/evidence_reviewed.csv",
            ROOT / "data/cache/research/ndx_v11_current_fundamental_evidence_v1/quality_input_readiness.csv",
            ROOT / "data/cache/research/ndx_v11_current_fundamental_evidence_v1/valuation_readiness.csv",
            ROOT / "data/cache/candidate_pools/security_candidate_registry_current.json",
        )
        cls.readiness = build_candidate_readiness(cls.frame, config=cls.config)

    def test_current_universe_is_real_securities_and_qqq_is_absent(self):
        self.assertEqual(len(self.readiness), 101)
        self.assertEqual(self.readiness["security_id"].nunique(), 101)
        self.assertNotIn("QQQ", set(self.readiness["ticker"]))
        self.assertEqual(int(self.readiness["role"].eq("incumbent_frozen").sum()), 7)
        self.assertNotIn("TSM", set(self.readiness["ticker"]))

    def test_final_current_taxonomy_is_used_but_admission_stays_closed(self):
        self.assertEqual(int(self.readiness["taxonomy_status"].eq("accepted").sum()), 91)
        self.assertEqual(int(self.readiness["live_eligible"].sum()), 0)
        self.assertTrue(self.readiness["blockers"].str.contains("FRESH_OOS_NOT_AVAILABLE").all())
        googl = self.readiness.loc[self.readiness["ticker"].eq("GOOGL")].iloc[0]
        self.assertIn("ISSUER_ALREADY_PRESENT_IN_INCUMBENT", googl["blockers"])

    def test_whole_lot_math_never_exceeds_target(self):
        actions = allocation_rows(
            self.readiness, new_money=3000.0, lot_size=1.0, fee_bps=10.0,
            minimum_fee=0.0, config=self.config,
            incumbent_risk_chains={"NVDA":"ai_accelerator","TXN":"analog_power","ASML":"semiconductor_equipment","CDNS":"eda_ip","TSM":"foundry","MU":"memory","MSFT":"cloud_application_software","GOOG":"platform_advertising"},
        )
        candidates = actions.loc[actions["ticker"].ne("")]
        spent = candidates["actual_candidate_amount"].fillna(0) + candidates["transaction_cost"].fillna(0)
        self.assertTrue((spent <= candidates["target_candidate_amount"] + 1e-9).all())
        self.assertEqual(set(candidates["target_candidate_share"]), {0.05, 0.10, 0.15})
        self.assertTrue(candidates["status"].eq("FORWARD_WATCH_ONLY_NOT_SELECTED").all())
        self.assertTrue(candidates["post_effective_n"].notna().all())

    def test_current_competition_narrows_actions_to_risk_chain_champions(self):
        attached = attach_current_competition(
            self.readiness,
            pd.read_csv(ROOT / "data/cache/research/ndx_v11_current_competition_v1/candidate_competition.csv"),
            pd.read_csv(ROOT / "data/cache/research/ndx_v11_current_competition_v1/risk_chain_shortlist.csv"),
        )
        actions = allocation_rows(
            attached, new_money=None, lot_size=1.0, fee_bps=10.0,
            minimum_fee=0.0,
        )
        candidate_actions = actions.loc[actions["ticker"].ne("")]
        self.assertEqual(attached["component_shortlisted"].sum(), 22)
        self.assertEqual(len(candidate_actions), 22 * 3)
        self.assertEqual(candidate_actions["ticker"].nunique(), 22)
        self.assertTrue(candidate_actions["status"].eq("FORWARD_WATCH_ONLY_NOT_SELECTED").all())


if __name__ == "__main__":
    unittest.main()
