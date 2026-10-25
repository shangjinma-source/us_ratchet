from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_rebinding_reader import RebindingDailyEvidenceReader
import test_strategy_daily_evidence_rebind as rebinding
import test_strategy_daily_signal_verifier as signals


class ReaderTests(unittest.TestCase):
    def fixture(self, bound=True):
        fixture=rebinding.RebindTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        signal_fixture=signals.SignalVerifierTests();signal_fixture.setUp()
        args=signal_fixture.args()
        root=Path(fixture.temp.name)
        release=args['release_bytes'];digest=sha256(release).hexdigest()
        parent=deepcopy(fixture.receipt)
        parent['release_sha256']=digest if bound else None
        encoded=canonical(parent)
        (root/'parent.json').write_bytes(encoded)
        (root/'release.json').write_bytes(release)
        (root/'calendar.json').write_bytes(args['calendar_bytes'])
        for name,raw in fixture.files.items():(root/name).write_bytes(raw)
        reader=RebindingDailyEvidenceReader(root=root,parent_receipt_path='parent.json',
            trusted_parent_sha256=sha256(encoded).hexdigest(),
            source_paths={p:p for p in fixture.files},release_path='release.json',
            trusted_release_sha256=digest,calendar_path='calendar.json')
        return fixture,reader,parent

    def test_cash_fill_and_target_change_reverify_without_changing_evidence(self):
        fixture,reader,parent=self.fixture()
        fixture.event('CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED')
        first=reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock)
        fixture.event('DIRECT_FILL',security_id='A',side='BUY',quantity=3,price='100',
                      fees='0',executed_at=fixture.clock.isoformat())
        fixture.event('CASH_CONFIRM',amount='1700',cash_basis='TOTAL_UNINVESTED')
        fixture.publish({'A':10})
        before=fixture.accounts.path.read_bytes()
        second=reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock)
        self.assertEqual(second['status'],'DAILY_SIGNAL_READY')
        self.assertEqual(second['signal']['effective_target_quantities'],{'A':5})
        self.assertNotEqual(first['signal']['account_revision'],second['signal']['account_revision'])
        self.assertEqual(second['source_received_at'],parent['source_received_at'])
        self.assertEqual(first['policy_release_sha256'],second['policy_release_sha256'])
        self.assertEqual(fixture.accounts.path.read_bytes(),before)

    def test_cross_day_new_security_and_absent_policy_are_explicit_waits(self):
        fixture,reader,_=self.fixture()
        result=reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock+timedelta(days=1))
        self.assertEqual((result['status'],result['reason']),('WAIT_FRESH_SIGNAL','WAIT_NEW_SESSION_EVIDENCE'))
        fixture.publish({'B':5})
        result=reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock)
        self.assertEqual((result['status'],result['reason']),('WAIT_SIGNAL','WAIT_NEW_SECURITY_EVIDENCE'))
        reader.release_path=None
        self.assertEqual(reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock)['status'],
                         'WAIT_POLICY_RELEASE')

    def test_unbound_review_cannot_be_silently_promoted(self):
        fixture,reader,_=self.fixture(bound=False)
        with self.assertRaisesRegex(ValueError,'REVIEWED_PARENT_POLICY_BINDING_REQUIRED'):
            reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock)

    def test_rebinding_does_not_skip_full_verifier_calendar_hash(self):
        fixture,reader,_=self.fixture()
        (Path(fixture.temp.name)/'calendar.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'FIXED_CALENDAR_HASH_MISMATCH'):
            reader(fixture.accounts.read(),fixture.targets.current(),fixture.clock)


if __name__=='__main__':
    unittest.main()
