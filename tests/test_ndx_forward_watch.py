from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from backtest.ndx_forward_watch import (
    _classification_from_frame,
    _price_status,
    build_bundle,
    build_sec_companyfacts_plan,
    load_forward_watch_spec,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxForwardWatchTests(unittest.TestCase):
    def test_registered_spec_locks_v10_and_excludes_qqq(self):
        spec = load_forward_watch_spec(ROOT / "config" / "ndx_v11_forward_watch.yaml")
        self.assertEqual(spec["fresh_oos_start"], "2026-07-13")
        self.assertFalse(spec["candidate_policy"]["qqq_candidate_allowed"])
        self.assertEqual(
            spec["rule_lock"]["valuation_policy_id"],
            "ndx_fcf_yield_overpay_guard_v1",
        )
        self.assertEqual(len(spec["rule_lock"]["frozen_profile_ids"]), 8)

    def test_historical_taxonomy_record_is_not_backfilled_to_forward_date(self):
        records = pd.DataFrame([
            {
                "ticker": "AAA",
                "status": "accepted",
                "security_id": "security:1:AAA",
                "issuer_id": "issuer:1",
                "risk_chain": "cloud_application_software",
                "confidence": "high",
                "effective_from": "2022-01-01",
                "effective_to": "2026-05-29",
                "evidence_available_date": "2022-01-02",
                "evidence_locator": "sec",
            }
        ])
        result = _classification_from_frame("AAA", "2026-07-13", records, None)
        self.assertEqual(result["status"], "unclassified")
        self.assertEqual(result["risk_chain"], "unclassified")

    def test_historical_observation_rejects_newer_current_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = build_bundle(
                spec_path=ROOT / "config" / "ndx_v11_forward_watch.yaml",
                live_config_path=ROOT / "config" / "config.yaml",
                output_dir=Path(directory),
                observation_date="2026-07-13",
                root=ROOT,
            )
            self.assertEqual(
                manifest["status"],
                "FORWARD_WATCH_REGISTRATION_BLOCKED_PREREQUISITE",
            )
            self.assertIn("ndx_current_snapshot", manifest["registration_blockers"])
            self.assertFalse(manifest["return_data_read"])
            self.assertFalse(manifest["candidate_admission_allowed"])
            self.assertEqual(manifest["summary"]["current_ndx_securities"], 101)
            self.assertEqual(manifest["summary"]["candidate_admission_allowed"], 0)
            observations = pd.read_csv(Path(directory) / "forward_observations.csv")
            self.assertNotIn("QQQ", set(observations["ticker"]))
            self.assertEqual(len(observations), 101)

    def test_companyfacts_plan_is_current_ndx_only(self):
        plan, audit = build_sec_companyfacts_plan(
            spec_path=ROOT / "config" / "ndx_v11_forward_watch.yaml",
            output_dir=ROOT / "data" / "cache" / "research" / "ndx_v11_forward_watch_v1",
            observation_date="2026-07-13",
            root=ROOT,
        )
        self.assertEqual(audit["ticker_count"], 101)
        self.assertNotIn("QQQ", set(plan["ticker"]))
        self.assertGreaterEqual(audit["unique_cik_count"], 95)

    def test_price_cache_must_end_strictly_before_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AAA.csv"
            dates = pd.bdate_range(end="2026-07-10", periods=504).tolist()
            dates.append(pd.Timestamp("2026-07-13"))
            pd.DataFrame({"Date": dates, "Close": [10.0] * len(dates)}).to_csv(
                path, index=False
            )
            status = _price_status(
                Path(directory), "AAA", "2026-07-09", "2026-07-13"
            )
            self.assertEqual(status["status"], "ready")
            self.assertEqual(status["end"], "2026-07-10")
            self.assertEqual(status["raw_end"], "2026-07-13")
            self.assertEqual(status["future_rows"], 1)


if __name__ == "__main__":
    unittest.main()
