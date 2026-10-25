from datetime import datetime,timedelta
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import pickle
import subprocess
import sys
import unittest
from unittest.mock import patch
import json
from data.strategy_prospective_paper_cap_store_v1 import ProspectivePersistentCaps,CODE_PATHS
from data.strategy_execution_limits_common_v1 import _build_execution_limits_core
from backtest.current_strategy_prospective_paper_book_v1 import project
from test_strategy_prospective_paper_integration_v1 import fixture
from test_strategy_prospective_paper_integration_v1 import execution
from data.strategy_prospective_paper_decision_v1 import produce_prospective_decision
from test_strategy_paper_execution_preview_v1 import capture


class PersistentPaperCapTests(unittest.TestCase):
    def setup_caps(self,folder):
        (Path(folder)/'sources').mkdir()
        daily=fixture(Path(folder)/'sources',extra_code_paths=CODE_PATHS)
        now=[datetime.fromisoformat('2026-11-03T15:00:10+00:00')]
        arguments=dict(root=folder,book=daily['book'],authority=daily['authority'],admitted_decisions={},clock=lambda:now[0].isoformat())
        return daily,now,arguments

    def build(self,daily,now,caps,price=1000):
        state=project(daily['book'],authority=daily['authority'],admitted_decisions={});state['orders']={}
        package,review=capture(daily['book'],now,price=price)
        return _build_execution_limits_core(state=state,target_quantities={'B':10},market_capture=package,
            unit_review=review,cap_store=caps,now=now.isoformat())

    def test_same_session_reopen_replays_original_cap_without_raising(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            cap=ProspectivePersistentCaps(**args,initialize=True);first=self.build(daily,now[0],cap)
            namespace=cap.namespace_id;cap.close()
            now[0]+=timedelta(seconds=10)
            reopened=ProspectivePersistentCaps(**args)
            self.assertEqual(reopened.namespace_id,namespace)
            second=self.build(daily,now[0],reopened,price=1100)
            self.assertLessEqual(Fraction(second['limits']['B']['buy']),Fraction(first['limits']['B']['buy']))
            self.assertEqual(reopened.proofs[-1]['cap_store_receipt']['prior_history_replayed'],1)
            self.assertNotEqual(second['limits']['B']['cap_record_hash'],first['limits']['B']['cap_record_hash'])

    def test_missing_truncated_or_partial_namespace_cannot_reset_cap(self):
        for mode in ('missing','truncated','pending'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                daily,now,args=self.setup_caps(folder)
                cap=ProspectivePersistentCaps(**args,initialize=True);self.build(daily,now[0],cap);cap.close()
                if mode=='missing':cap.path.unlink()
                elif mode=='truncated':cap.path.write_bytes(b'')
                else:cap.pending.write_bytes(b'preserve crash evidence')
                with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED|CHECKPOINT_CHANGED'):
                    ProspectivePersistentCaps(**args)
                with self.assertRaisesRegex(ValueError,'ALREADY_EXISTS'):
                    ProspectivePersistentCaps(**args,initialize=True)

    def test_real_hardlink_rejected_and_invalid_raw_rollback_retains_prior_cap(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            cap=ProspectivePersistentCaps(**args,initialize=True);first=self.build(daily,now[0],cap)
            before=cap.path.read_bytes();checkpoint=cap.checkpoint.read_bytes()
            with self.assertRaisesRegex(ValueError,'CAP_INPUT_NOT_NEWER'):self.build(daily,now[0],cap)
            self.assertEqual(cap.path.read_bytes(),before);self.assertEqual(cap.checkpoint.read_bytes(),checkpoint)
            self.assertFalse(cap.pending.exists())
            self.assertEqual(len(list(cap.path.parent.glob(cap.pending.name+'.no-commit-*'))),1)
            link=Path(folder)/'hardlink.sqlite';os.link(cap.path,link)
            with self.assertRaisesRegex(ValueError,'FILE_NOT_PRIVATE'):ProspectivePersistentCaps(**args)
            self.assertEqual(link.read_bytes(),before)

    def test_process_crash_after_cap_commit_preserves_recovery_marker(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            cap=ProspectivePersistentCaps(**args,initialize=True);self.build(daily,now[0],cap);cap.close()
            source=Path(folder)/'fixture.pickle'
            source.write_bytes(pickle.dumps(dict(daily=daily,root=folder,now=(now[0]+timedelta(seconds=10)).isoformat())))
            script="""import pickle,sys,os
from pathlib import Path
from datetime import datetime
sys.path.insert(0,'tests')
from test_strategy_prospective_paper_cap_store_v1 import PersistentPaperCapTests,ProspectivePersistentCaps
v=pickle.loads(Path(sys.argv[1]).read_bytes());d=v['daily']
cap=ProspectivePersistentCaps(root=v['root'],book=d['book'],authority=d['authority'],admitted_decisions={},clock=lambda:v['now'])
import data.strategy_prospective_paper_cap_store_v1 as storage
storage.os.replace=lambda *args:os._exit(73)
PersistentPaperCapTests().build(d,datetime.fromisoformat(v['now']),cap,price=1100)
"""
            child=subprocess.run([sys.executable,'-X','utf8','-E','-B','-c',script,str(source)],cwd=Path(__file__).resolve().parents[1],capture_output=True,timeout=30)
            self.assertEqual(child.returncode,73,child.stderr.decode(errors='replace'))
            self.assertTrue(cap.pending.exists())
            with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):ProspectivePersistentCaps(**args)
            pending_bytes=cap.pending.read_bytes();now[0]+=timedelta(seconds=20)
            recovered=ProspectivePersistentCaps(**args,recover_pending=True)
            self.assertEqual(recovered.recovery_report['action'],'INTENDED_CAP_COMMIT_REPLAYED')
            self.assertEqual(Path(recovered.recovery_report['preserved_intent_path']).read_bytes(),pending_bytes)
            self.assertFalse(recovered.recovery_report['reference_reissued'])
            next_result=self.build(daily,now[0],recovered,price=1200)
            self.assertLess(Fraction(next_result['limits']['B']['buy']),1000)
            self.assertEqual(recovered.proofs[-1]['cap_store_receipt']['prior_history_replayed'],2)

    def test_parallel_owner_lock_is_busy_without_any_cap_write(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            first=ProspectivePersistentCaps(**args,initialize=True);second=ProspectivePersistentCaps(**args)
            before=first.path.read_bytes()
            with first._locked():
                with self.assertRaisesRegex(ValueError,'PAPER_CAP_BUSY'):self.build(daily,now[0],second)
            self.assertEqual(first.path.read_bytes(),before);self.assertFalse(first.pending.exists())

    def test_formal_producer_uses_durable_namespace_after_reopen(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            cap=ProspectivePersistentCaps(**args,initialize=True)
            first=produce_prospective_decision(**execution(daily,args['clock'],caps=cap))
            cap.close();now[0]+=timedelta(seconds=10)
            reopened=ProspectivePersistentCaps(**args)
            second=produce_prospective_decision(**execution(daily,args['clock'],caps=reopened))
            self.assertEqual(second['decision']['cap_storage'],'DURABLE_REGISTERED_PAPER_CAP_V1')
            self.assertEqual(first['decision']['cap_namespace_id'],second['decision']['cap_namespace_id'])
            self.assertLessEqual(Fraction(second['new_orders'][0]['limit_price']),Fraction(first['new_orders'][0]['limit_price']))
            self.assertEqual(second['decision']['cap_proofs'][0]['cap_store_receipt']['prior_history_replayed'],1)

    def test_recovery_refuses_changed_append_intent_and_preserves_evidence(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            cap=ProspectivePersistentCaps(**args,initialize=True);self.build(daily,now[0],cap)
            now[0]+=timedelta(seconds=10)
            with patch('data.strategy_prospective_paper_cap_store_v1.os.replace',side_effect=OSError('checkpoint failed')):
                with self.assertRaises(OSError):self.build(daily,now[0],cap,price=1100)
            intent=json.loads(cap.pending.read_bytes());intent['request']['raw_blob']['sha256']='0'*64
            cap.pending.write_text(json.dumps(intent));before=cap.pending.read_bytes()
            with self.assertRaisesRegex(ValueError,'RECOVERY_SOURCE_CHANGED'):
                ProspectivePersistentCaps(**args,recover_pending=True)
            self.assertEqual(cap.pending.read_bytes(),before)

    def test_recovery_confirms_no_commit_without_resetting_history(self):
        with TemporaryDirectory() as folder:
            daily,now,args=self.setup_caps(folder)
            cap=ProspectivePersistentCaps(**args,initialize=True);self.build(daily,now[0],cap)
            before=cap.path.read_bytes();now[0]+=timedelta(seconds=10)
            with patch.object(cap.store,'candidate',side_effect=SystemExit(73)):
                with self.assertRaises(SystemExit):self.build(daily,now[0],cap,price=1100)
            reopened=ProspectivePersistentCaps(**args,recover_pending=True)
            self.assertEqual(reopened.recovery_report['action'],'NO_CAP_COMMIT_CONFIRMED')
            self.assertEqual(reopened.path.read_bytes(),before)
            self.build(daily,now[0],reopened,price=1100)
            self.assertEqual(reopened.proofs[-1]['cap_store_receipt']['prior_history_replayed'],1)

    def test_recovery_clock_before_intent_or_reversing_after_audit_preserves_failure(self):
        for mode in ('before_intent','during_audit'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                daily,now,args=self.setup_caps(folder)
                cap=ProspectivePersistentCaps(**args,initialize=True);self.build(daily,now[0],cap)
                now[0]+=timedelta(seconds=10)
                with patch.object(cap.store,'candidate',side_effect=SystemExit(73)):
                    with self.assertRaises(SystemExit):self.build(daily,now[0],cap,price=1100)
                saved={path:path.read_bytes() for path in (cap.pending,cap.path,cap.checkpoint)}
                if mode=='before_intent':
                    now[0]-=timedelta(seconds=5)
                else:
                    # Constructor, recovery start, then audit completion.
                    # Two samples would reject at start and miss the end check.
                    ticks=iter([now[0],now[0],now[0]-timedelta(seconds=1)])
                    readings=[]
                    def recovery_clock():
                        value=next(ticks);readings.append(value)
                        return value.isoformat()
                    args['clock']=recovery_clock
                with self.assertRaisesRegex(ValueError,'RECOVERY_CLOCK_REVERSED'):
                    ProspectivePersistentCaps(**args,recover_pending=True)
                if mode=='during_audit':self.assertEqual(len(readings),3)
                for path,raw in saved.items():self.assertEqual(path.read_bytes(),raw)
                self.assertFalse(list(cap.path.parent.glob(cap.path.name+'.recovery-*')))


if __name__=='__main__':unittest.main()
