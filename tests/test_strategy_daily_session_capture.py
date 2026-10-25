from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
import os
import subprocess

from data.strategy_daily_session_capture import capture_session, encoded


ROOT = Path(__file__).resolve().parents[1]


class DailySessionCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def pin(name, raw):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return dict(path=name, sha256=sha256(raw).hexdigest())
        security = dict(ticker="SNDK", security_id="security:0002023554:80004C200",
                        currency="USD", exchangeName="NMS", instrumentType="EQUITY")
        # Fixture authorization only. Never installed as a server release/review.
        identity = pin("fixture-identity.json", encoded(dict(schema="SERVER_CAPTURE_IDENTITY_V1",
                       review_status="REVIEWED", security=security)))
        calendar = pin("fixture-calendar.json", (ROOT / "tmp/daily_signal_sndk_reviewed_20261020_v1/calendar.json").read_bytes())
        pins = [pin(name, (ROOT / name).read_bytes()) for name in (
            "data/strategy_daily_session_capture.py",
            "data/current_quantity_v2_paper_action_sources.py",
            "scripts/current_research_official_alert_capture.py")]
        self.configuration = dict(schema="SERVER_DAILY_SESSION_CAPTURE_V1", calendar=calendar,
                                  identity_review=identity, security=security, source_pins=pins,
                                  output_root="capture")
        self.daily = (ROOT / "tmp/daily_signal_sndk_source_capture_20261020_v1/daily.response.bin").read_bytes()
        self.official = (ROOT / "tmp/daily_signal_sndk_source_capture_20261020_v1/official.response.bin").read_bytes()
        self.calls = []

    def run_capture(self, **overrides):
        raw = encoded(self.configuration)
        def daily(*args):
            self.calls.append("daily")
            return dict(status=200, body=self.daily)
        def official():
            self.calls.append("official")
            return dict(status=200, body=self.official)
        options = dict(root=self.root, configuration_bytes=raw,
                       configuration_sha256=sha256(raw).hexdigest(), execute=True,
                       fetch_daily=daily, fetch_official=official,
                       clock=lambda: datetime.fromisoformat("2026-10-20T12:00:00+00:00"))
        options.update(overrides)
        return capture_session(**options)

    def test_exact_twenty_and_second_attempt_never_fetches(self):
        result = self.run_capture()
        self.assertEqual(result["status"], "CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED")
        self.assertEqual(self.calls, ["daily", "official"])
        packet = json.loads((Path(result["output"]) / "candidate.json").read_bytes())
        self.assertEqual(len(packet["closes"]), 20)
        self.assertEqual(packet["market_asof"], "2026-10-19T16:00:00-04:00")
        self.assertTrue(packet["unit_review_required"])
        self.assertFalse(packet["policy_approved"])
        again = self.run_capture()
        self.assertEqual(again["http_calls"], 0)
        self.assertEqual(len(self.calls), 2)

    def test_failure_preserves_both_attempts_no_retry(self):
        self.daily = b'{"broken":true}'
        result = self.run_capture()
        self.assertEqual(result["status"], "WAIT_SOURCE_REVIEW")
        self.assertTrue((Path(result["output"]) / "daily.response.bin").exists())
        self.assertEqual(self.calls, ["daily", "official"])
        self.assertEqual(self.run_capture()["http_calls"], 0)

    def test_missing_prior_day_waits_without_fake_history(self):
        document = json.loads(self.daily)
        series = document["chart"]["result"][0]
        series["timestamp"].pop()
        series["indicators"]["quote"][0]["close"].pop()
        series["indicators"]["adjclose"][0]["adjclose"].pop()
        self.daily = encoded(document)
        result = self.run_capture()
        self.assertEqual(result["reason"], "WAIT_COMPLETE_TWENTY_SESSIONS")
        self.assertFalse((Path(result["output"]) / "candidate.json").exists())

    def test_new_day_without_pinned_calendar_does_not_reuse_old_capture(self):
        result = self.run_capture(clock=lambda: datetime.fromisoformat("2026-10-21T12:00:00+00:00"))
        self.assertEqual(result["status"], "WAIT_CALENDAR_SESSION")
        self.assertEqual(self.calls, [])

    def test_dry_run_no_files_and_identity_pin_mismatch(self):
        self.assertEqual(self.run_capture(execute=False)["status"], "DRY_RUN_NO_HTTP_NO_FILES")
        self.assertFalse((self.root / "capture").exists())
        self.configuration["security"]["ticker"] = "MU"
        with self.assertRaisesRegex(ValueError, "IDENTITY_REVIEW_REQUIRED"):
            self.run_capture()
        self.assertEqual(self.calls, [])

    def test_clock_backwards_before_request_counts_zero(self):
        times = iter(["2026-10-20T12:00:00+00:00"] + ["2026-10-20T11:59:00+00:00"] * 8)
        result = self.run_capture(clock=lambda: datetime.fromisoformat(next(times)))
        self.assertEqual(result["http_calls"], 0)
        self.assertEqual([r["attempts"] for r in result["results"].values()], [0, 0])
        self.assertEqual(self.calls, [])

    def test_clock_backwards_before_second_request_counts_one(self):
        times = iter(["2026-10-20T12:00:00+00:00"] * 3 + ["2026-10-20T11:59:00+00:00"] * 8)
        result = self.run_capture(clock=lambda: datetime.fromisoformat(next(times)))
        self.assertEqual(result["http_calls"], 1)
        self.assertEqual([r["attempts"] for r in result["results"].values()], [1, 0])
        self.assertEqual(self.calls, ["daily"])

    def test_daily_crosses_close_no_second_request(self):
        times = iter(["2026-10-20T19:59:58+00:00", "2026-10-20T19:59:59+00:00"] +
                     ["2026-10-20T20:00:01+00:00"] * 8)
        result = self.run_capture(clock=lambda: datetime.fromisoformat(next(times)))
        self.assertEqual(result["http_calls"], 1)
        self.assertEqual(result["results"]["official"]["attempts"], 0)
        self.assertEqual(self.calls, ["daily"])

    def make_alias(self):
        actual = self.root / "actual"
        actual.mkdir()
        alias = self.root / "alias"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(actual)],
                           check=True, capture_output=True)
        else:
            alias.symlink_to(actual, target_is_directory=True)
        return actual, alias

    def test_same_root_output_alias_rejected(self):
        self.make_alias()
        self.configuration["output_root"] = "alias/capture"
        with self.assertRaisesRegex(ValueError, "PATH_ALIAS_FORBIDDEN"):
            self.run_capture()
        self.assertEqual(self.calls, [])

    def test_same_root_source_alias_rejected(self):
        actual, _ = self.make_alias()
        original = self.configuration["identity_review"]
        (actual / "identity.json").write_bytes((self.root / original["path"]).read_bytes())
        self.configuration["identity_review"] = dict(original, path="alias/identity.json")
        with self.assertRaisesRegex(ValueError, "PATH_ALIAS_FORBIDDEN"):
            self.run_capture()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
