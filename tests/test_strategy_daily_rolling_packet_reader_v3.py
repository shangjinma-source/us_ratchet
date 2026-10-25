import json
import unittest
from datetime import timedelta
from hashlib import sha256

from core.strategy_account_ledger import canonical
from data.strategy_daily_rolling_packet_reader_v3 import RollingSessionDailyPacketReaderV3
import test_strategy_daily_rolling_runner_v3 as fixtures


class RollingPacketReaderTests(unittest.TestCase):
    def setUp(self):
        self.runner = fixtures.RollingRunnerTests()
        self.runner.setUp()
        self.addCleanup(self.runner.doCleanups)
        self.root = self.runner.root
        raw = canonical(self.runner.config)
        (self.root / "reader-config.json").write_bytes(raw)
        self.reader = RollingSessionDailyPacketReaderV3(
            root=self.root, configuration_path="reader-config.json",
            configuration_sha256=sha256(raw).hexdigest(), archive_root="archive",
        )

    def read(self):
        fixture = self.runner.f.f
        return self.reader(fixture.accounts.read(), fixture.target, fixture.now)

    def test_two_days_real_packet_chain_no_policy_promotion(self):
        for day in ("2026-10-21", "2026-10-22"):
            self.assertEqual(self.runner.run_day(day)["status"],
                             "DAILY_CONDITIONAL_PACKET_SAVED")
            count = len(self.runner.calls)
            self.assertEqual(self.read()["status"], "WAIT_POLICY_RELEASE")
            self.assertEqual(len(self.runner.calls), count)

    def test_current_packet_cannot_fallback_when_parent_fails(self):
        self.runner.run_day("2026-10-21")
        self.runner.run_day("2026-10-22")
        path = self.root / "runs/2026-10-21/terminal.json"
        terminal = json.loads(path.read_bytes())
        terminal["status"] = "NEEDS_RECOVERY"
        path.write_bytes(canonical(terminal))
        with self.assertRaisesRegex(ValueError, "WAIT_PREVIOUS_SESSION_RECOVERY"):
            self.read()

    def test_future_terminal_and_changed_parent_rejected(self):
        self.runner.run_day("2026-10-21")
        path = self.root / "runs/2026-10-21/terminal.json"
        original = json.loads(path.read_bytes())
        terminal = dict(original, finished_at=(
            self.runner.f.f.now + timedelta(seconds=1)).isoformat())
        path.write_bytes(canonical(terminal))
        with self.assertRaisesRegex(ValueError, "PACKET_AVAILABILITY_CHANGED"):
            self.read()
        terminal = dict(original, parent={"kind": "UNREVIEWED"})
        path.write_bytes(canonical(terminal))
        with self.assertRaisesRegex(ValueError, "PACKET_PARENT_CHANGED"):
            self.read()

    def test_profile_bridge_waits_without_release_and_rejects_unapproved_release(self):
        from data.strategy_profiled_rolling_packet_admission_v3 import ProfiledRollingSessionDailyReaderV3
        self.runner.run_day("2026-10-21")
        options = dict(root=self.root, configuration_path="reader-config.json",
                       configuration_sha256=self.reader.configuration["sha256"],
                       archive_root="archive")
        self.reader = ProfiledRollingSessionDailyReaderV3(**options)
        self.assertEqual(self.read()["status"], "WAIT_POLICY_RELEASE")
        raw = canonical({"schema": "SERVER_DAILY_POLICY_RELEASE_V1", "approved": False})
        (self.root / "unapproved-release.json").write_bytes(raw)
        self.reader = ProfiledRollingSessionDailyReaderV3(
            **options, release_path="unapproved-release.json",
            trusted_release_sha256=sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError, "PROFILE_RELEASE_NOT_APPROVED"):
            self.read()


if __name__ == "__main__":
    unittest.main()
