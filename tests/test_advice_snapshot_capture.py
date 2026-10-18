from __future__ import annotations

import unittest

from scripts.advice_snapshot_capture import summarize_capture_payload


class AdviceSnapshotCaptureTests(unittest.TestCase):
    def test_requires_durable_snapshot_confirmation(self):
        payload = {
            "as_of": "2026-07-15",
            "latest_closed_session_date": "2026-07-14",
            "state_last_run_date": "2026-07-01",
            "state_freshness": {"status": "DAILY_UPDATE_REQUIRED"},
            "market": {"regime": "NEUTRAL"},
            "execution": {"actionable_count": 0, "counts": {"WAIT": 8}},
            "advice_snapshot": {
                "logged": True,
                "snapshot_id": "2026-07-15-1",
                "ts": "2026-07-15T10:00:00",
                "path": "data/advice_snapshots.jsonl",
            },
        }
        result = summarize_capture_payload(payload)
        self.assertTrue(result["captured"])
        self.assertEqual(result["snapshot_id"], "2026-07-15-1")
        self.assertEqual(result["state_status"], "DAILY_UPDATE_REQUIRED")
        self.assertEqual(result["latest_closed_session_date"], "2026-07-14")

    def test_rejects_response_when_journal_write_failed(self):
        with self.assertRaises(RuntimeError):
            summarize_capture_payload({"advice_snapshot": {"logged": False, "error": "disk"}})


if __name__ == "__main__":
    unittest.main()
