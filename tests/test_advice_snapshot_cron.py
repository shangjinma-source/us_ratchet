from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.advice_snapshot_cron import is_us_capture_window, run_scheduled_capture


class AdviceSnapshotCronTests(unittest.TestCase):
    def test_market_window_is_dst_aware_and_weekday_only(self):
        self.assertTrue(is_us_capture_window(datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)))
        self.assertFalse(is_us_capture_window(datetime(2026, 7, 18, 14, 0, tzinfo=timezone.utc)))
        self.assertTrue(is_us_capture_window(datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)))
        self.assertFalse(is_us_capture_window(datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc)))

    def test_success_resets_counter_and_writes_durable_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            counter = root / "counter"
            audit = root / "audit.jsonl"
            alert = root / "alert.json"
            counter.write_text("2\n", encoding="utf-8")
            payload, code = run_scheduled_capture(
                lambda: {"captured": True, "snapshot_id": "snap-1"},
                counter_path=counter,
                audit_path=audit,
                alert_path=alert,
                retry_delay_seconds=0,
            )
            self.assertEqual(code, 0)
            self.assertTrue(payload["captured"])
            self.assertEqual(counter.read_text(encoding="utf-8"), "0\n")
            self.assertTrue(json.loads(audit.read_text(encoding="utf-8"))["ok"])
            self.assertFalse(json.loads(alert.read_text(encoding="utf-8"))["active"])

    def test_third_consecutive_failure_requests_alert_and_resets_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            counter = root / "counter"
            audit = root / "audit.jsonl"
            alert = root / "alert.json"
            counter.write_text("2\n", encoding="utf-8")

            def fail():
                raise ConnectionError("api unavailable")

            payload, code = run_scheduled_capture(
                fail,
                counter_path=counter,
                audit_path=audit,
                alert_path=alert,
                attempts=2,
                retry_delay_seconds=0,
                alert_after=3,
            )
            self.assertEqual(code, 2)
            self.assertTrue(payload["alert_required"])
            self.assertEqual(payload["consecutive_failures"], 3)
            self.assertEqual(counter.read_text(encoding="utf-8"), "0\n")
            self.assertEqual(len(payload["error_history"]), 2)
            persisted_alert = json.loads(alert.read_text(encoding="utf-8"))
            self.assertTrue(persisted_alert["active"])
            self.assertEqual(
                persisted_alert["alert_type"], "ADVICE_SNAPSHOT_CAPTURE_FAILED"
            )


if __name__ == "__main__":
    unittest.main()
