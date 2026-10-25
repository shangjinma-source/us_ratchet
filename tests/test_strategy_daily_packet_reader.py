import json
from datetime import timedelta
from hashlib import sha256
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_packet_reader import CurrentSessionDailyPacketReader
import test_strategy_daily_source_runner as fixtures


class PacketReaderTests(unittest.TestCase):
    def setUp(self):
        self.runner=fixtures.RunnerTests()
        self.runner.setUp()
        self.addCleanup(self.runner.doCleanups)
        self.f=self.runner.fixture
        raw=canonical(self.runner.config)
        (self.f.root/"pipeline.json").write_bytes(raw)
        self.options=dict(root=self.f.root,configuration_path="pipeline.json",
            configuration_sha256=sha256(raw).hexdigest(),archive_root=self.f.root/"archive")

    def read(self, **options):
        return CurrentSessionDailyPacketReader(**dict(self.options,**options))(
            self.f.accounts.read(),self.f.target,self.f.now)

    def test_complete_null_release_stays_wait_and_no_account_writes(self):
        self.runner.run_pipeline()
        before=self.f.accounts.path.read_bytes()
        self.assertEqual(self.read()["status"],"WAIT_POLICY_RELEASE")
        self.assertEqual(self.f.accounts.path.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,"REVIEWED_PARENT_POLICY_BINDING_REQUIRED"):
            self.read(release_path="invented.json",trusted_release_sha256="a"*64)

    def test_missing_today_never_uses_yesterday(self):
        self.runner.run_pipeline()
        self.f.now+=timedelta(days=1)
        self.assertEqual(self.read()["status"],"WAIT_FRESH_SIGNAL")

    def test_source_tamper_and_incomplete_terminal_block(self):
        result=self.runner.run_pipeline()
        manifest=json.loads((self.f.root/result["manifest_reference"]["path"]).read_bytes())
        ref=next(iter(manifest.values()))
        (self.f.root/ref["path"]).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError,"SOURCE_HASH_CHANGED"):
            self.read()
        terminal=self.f.root/"runs/2026-10-20/terminal.json"
        terminal.write_bytes(canonical(dict(status="NEEDS_RECOVERY")))
        self.assertEqual(self.read()["reason"],"DAILY_PACKET_NEEDS_RECOVERY")


if __name__=="__main__":
    unittest.main()
