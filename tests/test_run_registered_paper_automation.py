from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_run_registered_quantity_v2_paper_simulation as fixtures
from scripts import run_registered_paper_automation as automation


def setup(folder,existing=True):
    args,request,now,store,save=fixtures.bundle(folder,existing)
    root=Path(folder);pins={}
    for name,where in automation.REQUIRED.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(where()).read_bytes());pins[name]=sha256(target.read_bytes()).hexdigest()
    policy=save('policy.json',dict(request_sha256=args['expected_request_sha256'],registration_directory='registration',source_hashes={}))
    descriptor=save('automation.json',dict(schema='REGISTERED_PAPER_AUTOMATION_V1',root=str(root),registration_directory='registration',request_sha256=args['expected_request_sha256'],publication_policy=policy,source_hashes=pins,log_directory='auto-logs'))
    return dict(descriptor_path=root/'automation.json',expected_descriptor_sha256=descriptor['sha256'],clock=lambda:now),now,store

class AutomationTests(unittest.TestCase):
    def test_shared_lock_contention_is_reviewable_not_a_poisoned_attempt(self):
        with TemporaryDirectory() as folder:
            args,_,store=setup(folder);before=store.path.read_bytes()
            lock=Path(folder)/automation.registrar.LOCK;lock.parent.mkdir(parents=True,exist_ok=True);lock.write_text('unknown-owner')
            with patch.object(automation.runtime,'run',side_effect=AssertionError('must not dispatch')):
                result=automation.run(**args,mode='daily',execute=True)
            self.assertEqual(result['status'],'LOCK_PRESENT_REVIEW_REQUIRED')
            self.assertFalse((Path(folder)/'auto-logs').exists())
            lock.unlink() # fixture owner clears its own lock
            with patch.object(automation.runtime,'run',side_effect=ValueError('RUN_LOCK_PRESENT_REVIEW_IF_STALE')):
                self.assertEqual(automation.run(**args,mode='daily',execute=True)['strategy_dispatches'],0)
            self.assertFalse(list((Path(folder)/'auto-logs').rglob('failed.json')))
            self.assertEqual(automation.run(**args,mode='daily',execute=True)['status'],'SKIPPED_NO_DISPATCH')
            self.assertEqual(store.path.read_bytes(),before)

    def test_missing_current_month_route_never_falls_back(self):
        with TemporaryDirectory() as folder:
            args,now,store=setup(folder);before=store.path.read_bytes()
            with patch.object(automation.runtime,'load_bundle',wraps=automation.runtime.load_bundle) as load:
                original=load._mock_wraps
                def prior_start(**kwargs):
                    value=original(**kwargs);value['request']['evaluation']['start_session']='2026-09-01';return value
                load.side_effect=prior_start
                with patch.object(automation.runtime,'audit_runtime_receipts',return_value={'state':{}}),patch.object(automation.runtime,'inspect_admission',return_value={'phase':'DAILY_ELIGIBLE_NOT_EXECUTED'}),patch.object(automation.publisher,'run',return_value={'status':'PREFLIGHT_ONLY'}) as publish,patch.object(automation.runtime,'run',side_effect=AssertionError('no fallback')):
                    with self.assertRaisesRegex(ValueError,'CURRENT_MONTH_APPROVED_ROUTE_MISSING'):automation.run(**args,mode='daily',execute=True)
                    self.assertEqual(publish.call_args.kwargs['target_month'],'2026-10')
            self.assertEqual(store.path.read_bytes(),before)

    def test_cli_waiting_and_unknown_states(self):
        args=['--descriptor-path','unused','--expected-descriptor-sha256','unused','--mode','monthly']
        for status,expected in [('WAITING_ACCOUNT',0),('WAITING_SESSION_CLOSE',0),('WAITING_REVIEW',2),('RECOVERY_REQUIRED',2),('LOCK_PRESENT_REVIEW_REQUIRED',2),('UNKNOWN',2)]:
            with self.subTest(status=status),patch.object(automation,'run',return_value={'status':status}),patch('builtins.print'):
                self.assertEqual(automation.main(args),expected)

    def test_initial_month_and_finalization_do_not_require_monthly_route(self):
        with TemporaryDirectory() as folder:
            args,now,store=setup(folder);before=store.path.read_bytes()
            with patch.object(automation.publisher,'run',side_effect=AssertionError('no route needed')):
                first=automation.run(**args,mode='daily',execute=True)
                self.assertEqual(first['status'],'SKIPPED_NO_DISPATCH')
                later=dict(args,clock=lambda:now+timedelta(hours=8))
                with patch.object(automation.runtime,'run',return_value={'status':'COMPLETE'}) as runtime:
                    self.assertEqual(automation.run(**later,mode='daily',execute=True)['status'],'COMPLETE')
                    self.assertNotIn('route_path',runtime.call_args.kwargs)
            self.assertEqual(store.path.read_bytes(),before)

    def test_no_account_monthly_does_not_bootstrap_and_preview_writes_nothing(self):
        with TemporaryDirectory() as folder:
            args,now,store=setup(folder,False);before=sorted(str(p) for p in Path(folder).rglob('*'))
            self.assertEqual(automation.run(**args,mode='monthly',execute=True)['status'],'WAITING_ACCOUNT')
            self.assertEqual(automation.run(**args,mode='daily')['status'],'PREFLIGHT_ONLY')
            self.assertEqual(before,sorted(str(p) for p in Path(folder).rglob('*')))

    def test_source_drift_and_orphan_attempt_fail_closed(self):
        with TemporaryDirectory() as folder:
            args,_,_=setup(folder)
            logs=Path(folder)/'auto-logs/old';logs.mkdir(parents=True);(logs/'started.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'PARTIAL_RUN'):automation.run(**args,mode='daily',execute=True)
            (Path(folder)/'scripts/run_registered_paper_automation.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):automation.run(**args,mode='daily')

if __name__=='__main__':unittest.main()
