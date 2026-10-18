from __future__ import annotations

import unittest
from pathlib import Path

from backtest.ndx_marginal_dashboard import read_verified_marginal_dashboard


ROOT = Path(__file__).resolve().parents[1]


class NdxMarginalDashboardTests(unittest.TestCase):
    def test_real_bundle_separates_current_structure_from_frozen_seed(self):
        payload = read_verified_marginal_dashboard(
            stage1_dir=ROOT / "data/cache/research/ndx_marginal_stage1_v1",
            forward_dir=ROOT / "data/cache/research/ndx_marginal_forward_v1",
            overlay_path=ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/evidence_reviewed.csv",
            event_gap_manifest_path=ROOT / "data/cache/candidate_pools/ndx_history/event_gap_disposition/manifest.json",
        )
        current = payload["current_structure"]
        forward = payload["frozen_forward"]
        self.assertTrue(payload["available"])
        self.assertFalse(payload["candidate_admission_allowed"])
        self.assertEqual(current["candidate_count"], 22)
        self.assertEqual(current["action_count"], 67)
        self.assertEqual(current["new_money_status"], "NOT_PROVIDED_NO_USD_OR_SHARE_GUESS")
        self.assertEqual(len(current["actions"]), 67)
        self.assertEqual(forward["cohort_origin"], "imported_seed")
        self.assertFalse(forward["cohort_fresh_oos_eligible"])
        self.assertEqual(forward["fresh_primary_mature_windows"], 0)
        # The forward recorder appends one point per action/session, so this
        # count grows as new sessions arrive.  The manifest reader above
        # already verifies the exact current row count and content hash.
        self.assertGreater(len(forward["curve_points"]), 0)
        self.assertEqual(
            len({row["action_id"] for row in forward["curve_points"]}),
            current["action_count"],
        )
        event_gate = payload["event_evidence_gate"]
        self.assertTrue(event_gate["scope_lock_complete"])
        self.assertFalse(event_gate["historical_backtest_allowed"])
        self.assertFalse(event_gate["v11_execution_allowed"])
        self.assertEqual(event_gate["partial_exact_addition_count"], 1)
        gral = next(row for row in event_gate["cases"] if row["ticker"] == "GRAL")
        self.assertTrue(gral["exact_addition_supported"])
        self.assertFalse(gral["exact_removal_date_supported"])
        self.assertTrue(all(
            row["evidence_role"]
            == "FORWARD_CURVE_MONITORING_ONLY_NOT_ADMISSION_EVIDENCE"
            for row in forward["curve_points"]
        ))
        tickers = {row["ticker"] for row in current["candidates"]}
        self.assertIn("KLAC", tickers)
        self.assertIn("GILD", tickers)


if __name__ == "__main__":
    unittest.main()
