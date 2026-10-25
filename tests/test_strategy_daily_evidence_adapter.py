import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from data.strategy_daily_evidence_adapter import SavedDailyEvidenceAdapter
import test_strategy_daily_signal_verifier as signal_fixtures
import test_strategy_daily_preview_service as preview_fixtures


class EvidenceAdapterTests(unittest.TestCase):
    def test_missing_release_is_wait_policy_in_real_sqlite_preview(self):
        fixture=preview_fixtures.DailyPreviewTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        adapter=SavedDailyEvidenceAdapter(root=fixture.temp.name)
        fixture.service.signal_verifier=adapter
        fixture.service.policy_id=None
        before=fixture.account.path.read_bytes()
        result=fixture.service.preview()
        self.assertEqual(result['status'],'WAIT_POLICY_RELEASE')
        self.assertEqual(fixture.calls,0)
        self.assertEqual(fixture.account.path.read_bytes(),before)

    def test_pinned_fixture_roundtrip_tampering_and_path_escape(self):
        fixture=signal_fixtures.SignalVerifierTests()
        fixture.setUp()
        args=fixture.args()
        with TemporaryDirectory() as temp:
            root=Path(temp)
            for name,key in [('release.json','release_bytes'),('receipt.json','receipt_bytes'),
                             ('calendar.json','calendar_bytes')]:
                (root/name).write_bytes(args[key])
            for name,body in args['files'].items():
                (root/name).write_bytes(body)
            adapter=SavedDailyEvidenceAdapter(root=root,release_path='release.json',
                trusted_release_sha256=args['trusted_release_sha256'],receipt_path='receipt.json',
                trusted_receipt_sha256=args['trusted_receipt_sha256'],calendar_path='calendar.json',
                source_paths={name:name for name in args['files']})
            now=datetime.fromisoformat(args['now'])
            self.assertEqual(adapter.verify(args['state'],args['target'],now)['status'],'DAILY_SIGNAL_READY')
            (root/'normalized.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                adapter.verify(args['state'],args['target'],now)
            adapter.source_paths={'outside':'../outside.json'}
            with self.assertRaises(ValueError):
                adapter.verify(args['state'],args['target'],now)


if __name__=='__main__':
    unittest.main()
