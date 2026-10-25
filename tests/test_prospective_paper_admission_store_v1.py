from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import multiprocessing
import os

from backtest.current_strategy_prospective_paper_admission_store_v1 import ProspectivePaperAdmissionStore,SOURCE
from data.strategy_prospective_paper_cap_store_v1 import ProspectivePersistentCaps
from test_strategy_prospective_paper_integration_v1 import execution
import test_strategy_prospective_paper_daily_capture_v1 as daily_fixture
from data.strategy_prospective_paper_daily_capture_v1 import capture_prospective_daily


def crash_archive(root,authority,arguments,anchor,phase):
    clock=lambda:datetime.fromisoformat('2026-11-03T15:00:10+00:00')
    daily=arguments['daily_arguments']
    caps=ProspectivePersistentCaps(root=root,book=daily['book'],authority=authority,
        admitted_decisions=daily['admitted_decisions'],clock=lambda:clock().isoformat())
    arguments['caps']=caps
    def fault(at):
        if at==phase:os._exit(79)
    store=ProspectivePaperAdmissionStore(root=root,authority=authority,clock=clock,fault=fault)
    store.produce_and_archive_decision('crash-'+phase,arguments,daily_archive=anchor)


class AdmissionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        with patch.object(daily_fixture,'CODE_PATHS',daily_fixture.CODE_PATHS|{SOURCE}):
            arguments,_=daily_fixture.arguments(self.temp.name)
        captured=capture_prospective_daily(**arguments)
        self.daily=captured['daily_arguments']
        self.anchor=dict(directory=captured['directory'],trusted_complete_sha256=captured['archive_complete_sha256'])
        self.now='2026-11-03T15:00:10+00:00'
        self.caps=ProspectivePersistentCaps(root=self.temp.name,book=self.daily['book'],authority=self.daily['authority'],
            admitted_decisions={},clock=lambda:self.now,initialize=True)
        self.addCleanup(self.caps.close)
        self.arguments=execution(self.daily,lambda:self.now,caps=self.caps);self.arguments.pop('clock')
        self.store=self.make();self.store.initialize()

    def make(self,**kwargs):
        return ProspectivePaperAdmissionStore(root=self.temp.name,authority=self.daily['authority'],
            clock=lambda:datetime.fromisoformat(self.now),**kwargs)

    def test_internal_producer_archive_reopen_loader_and_idempotence_without_cap_side_effect(self):
        result=self.store.produce_and_archive_decision('daily-first',self.arguments,daily_archive=self.anchor)
        self.assertEqual(result['status'],'VERIFIED_PROSPECTIVE_PAPER_EXECUTION_DECISION')
        cap_hash=sha256(self.caps.path.read_bytes()).hexdigest()
        with patch('backtest.current_strategy_prospective_paper_admission_store_v1.produce_prospective_decision',
                   side_effect=AssertionError('loader or retry reran producer')):
            loaded=self.make().load()
            self.assertEqual(loaded,dict(decisions={result['decision_sha256']:result['decision_bytes']},settlements={}))
            self.assertEqual(self.make().produce_and_archive_decision('daily-first',self.arguments,daily_archive=self.anchor),result)
        self.assertEqual(sha256(self.caps.path.read_bytes()).hexdigest(),cap_hash)

    def test_failed_producer_preserves_marker_and_never_admits(self):
        invalid=dict(self.arguments);invalid['trusted_execution_admission_sha256']='0'*64
        with self.assertRaises(ValueError):self.store.produce_and_archive_decision('invalid',invalid,daily_archive=self.anchor)
        directory=self.store.directory/sha256(b'invalid').hexdigest()
        self.assertTrue((directory/'failed.json').is_file())
        self.assertEqual(self.make().load(),{'decisions':{},'settlements':{}})
        with self.assertRaisesRegex(ValueError,'PARTIAL_REQUIRES_RECOVERY'):
            self.store.produce_and_archive_decision('invalid',invalid,daily_archive=self.anchor)

    def test_archive_before_registration_is_not_admitted_or_blindly_retried(self):
        def fail(phase):
            if phase=='after_archive':raise RuntimeError('simulated crash boundary')
        with self.assertRaisesRegex(RuntimeError,'crash'):
            self.make(fault=fail).produce_and_archive_decision('partial',self.arguments,daily_archive=self.anchor)
        self.assertEqual(self.make().load(),{'decisions':{},'settlements':{}})
        with self.assertRaisesRegex(ValueError,'PARTIAL_REQUIRES_RECOVERY'):
            self.make().produce_and_archive_decision('partial',self.arguments,daily_archive=self.anchor)

    def test_commit_response_loss_is_recoverable_without_reproduction(self):
        def fail(phase):
            if phase=='after_commit':raise RuntimeError('response lost')
        with self.assertRaisesRegex(RuntimeError,'response lost'):
            self.make(fault=fail).produce_and_archive_decision('committed',self.arguments,daily_archive=self.anchor)
        with patch('backtest.current_strategy_prospective_paper_admission_store_v1.produce_prospective_decision',
                   side_effect=AssertionError('must not repeat cap operation')):
            result=self.make().produce_and_archive_decision('committed',self.arguments,daily_archive=self.anchor)
        self.assertIn(result['decision_sha256'],self.make().load()['decisions'])

    def test_source_blob_manifest_and_foreign_authority_rejected(self):
        self.store.produce_and_archive_decision('first',self.arguments,daily_archive=self.anchor)
        directory=self.store.directory/sha256(b'first').hexdigest()
        blob=next((directory/'blobs').iterdir());old=blob.read_bytes();blob.write_bytes(old+b'changed')
        with self.assertRaisesRegex(ValueError,'BLOB_CHANGED'):self.make().load()
        blob.write_bytes(old)
        (directory/'complete.json').write_bytes((directory/'complete.json').read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'MANIFEST_CHANGED'):self.make().load()
        invalid=dict(self.arguments);invalid['daily_arguments']=deepcopy(invalid['daily_arguments'])
        invalid['daily_arguments']['authority']['trusted_registration_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'AUTHORITY_CHANGED'):
            self.make().produce_and_archive_decision('foreign',invalid,daily_archive=self.anchor)

    def test_real_process_crash_before_and_after_sqlite_commit(self):
        for phase,expected in [('after_archive',0),('before_commit',0),('after_commit',1)]:
            case=AdmissionStoreTests();case.setUp()
            try:
                arguments={k:v for k,v in case.arguments.items() if k!='caps'}
                case.caps.close()
                process=multiprocessing.get_context('spawn').Process(target=crash_archive,
                    args=(case.temp.name,case.daily['authority'],arguments,case.anchor,phase))
                process.start();process.join(20)
                self.assertFalse(process.is_alive());self.assertEqual(process.exitcode,79)
                loaded=case.make().load();self.assertEqual(len(loaded['decisions']),expected)
                caps=ProspectivePersistentCaps(root=case.temp.name,book=case.daily['book'],authority=case.daily['authority'],
                    admitted_decisions={},clock=lambda:case.now)
                case.addCleanup(caps.close);arguments['caps']=caps
                if expected:
                    with patch('backtest.current_strategy_prospective_paper_admission_store_v1.produce_prospective_decision',
                               side_effect=AssertionError('committed replay must not reproduce')):
                        result=case.make().produce_and_archive_decision('crash-'+phase,arguments,daily_archive=case.anchor)
                    self.assertIn(result['decision_sha256'],case.make().load()['decisions'])
                else:
                    with self.assertRaisesRegex(ValueError,'PARTIAL_REQUIRES_RECOVERY'):
                        case.make().produce_and_archive_decision('crash-'+phase,arguments,daily_archive=case.anchor)
            finally:case.doCleanups()

    def test_daily_complete_anchor_is_required_even_after_registration(self):
        self.store.produce_and_archive_decision('first',self.arguments,daily_archive=self.anchor)
        Path(self.anchor['directory'],'failed.json').write_text('{}',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'DAILY_FAILED'):self.make().load()


if __name__=='__main__':unittest.main()
