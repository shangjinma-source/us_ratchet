from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.ndx_marginal_forward_daily import is_safe_post_close_window, run_daily


class NdxMarginalForwardDailyTests(unittest.TestCase):
    def test_post_close_window_is_dst_aware(self):
        self.assertTrue(is_safe_post_close_window(datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc)))
        self.assertTrue(is_safe_post_close_window(datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc)))
        self.assertFalse(is_safe_post_close_window(datetime(2026, 7, 16, 20, 0, tzinfo=timezone.utc)))

    def test_success_runs_refresh_then_evaluation_and_writes_status(self):
        calls = []

        def succeed(command, timeout):
            calls.append((command, timeout))
            return {"command": command, "returncode": 0, "stdout": "ok", "stderr": ""}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload, code = run_daily(
                audit_path=root / "audit.jsonl",
                status_path=root / "status.json",
                timeout_seconds=10,
                runner=succeed,
            )
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(len(calls), 2)
            self.assertIn("ndx_marginal_forward_refresh.py", calls[0][0][2])
            self.assertEqual(calls[1][0][-1], "evaluate")
            self.assertTrue((root / "status.json").exists())

    def test_failure_stops_before_evaluation(self):
        calls = []

        def fail(command, timeout):
            calls.append(command)
            return {"command": command, "returncode": 2, "stdout": "", "stderr": "failed"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload, code = run_daily(
                audit_path=root / "audit.jsonl",
                status_path=root / "status.json",
                runner=fail,
            )
            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertEqual(len(calls), 1)
            self.assertFalse(payload["live_config_changed"])
            self.assertFalse(payload["state_changed"])


if __name__ == "__main__":
    unittest.main()
