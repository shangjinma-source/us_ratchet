"""Orchestration trust checks; admission/dispatch seams are explicit, no economic run."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from test_run_registered_paper_automation import setup
from scripts import run_registered_paper_automation as auto


class AutomationProofReview(unittest.TestCase):
    def test_route_inputs_rechecked_under_dispatch_lock(self):
        for changed in ('evidence','route','proof'):
            with self.subTest(changed=changed),TemporaryDirectory() as folder:
                args,now,store=setup(folder);root=Path(folder)
                original=auto.runtime.load_bundle
                descriptor=json.loads(args['descriptor_path'].read_bytes())
                validated=original(root=root,registration_directory='registration',expected_request_sha256=descriptor['request_sha256'],now=now)
                # Only force route selection to isolate outer proof gate. Real
                # core month checks are separately covered by wrapper tests.
                validated['request']['evaluation']['start_session']='2025-01-01'
                evidence=root/'route-input';evidence.write_bytes(b'approved')
                route=root/'route.json';route.write_text('{}')
                proof=root/'complete.json';proof.write_text(json.dumps({'input_hashes':{'route-input':sha256(evidence.read_bytes()).hexdigest()}}))
                published=dict(status='POLICY_AUTHORIZED_ROUTE',route_path=str(route),route_sha256=sha256(route.read_bytes()).hexdigest())
                before=store.path.read_bytes();seen=[]
                def dispatch(**options):
                    lock=root/auto.registrar.LOCK;lock.parent.mkdir(parents=True,exist_ok=True);lock.write_bytes(b'test-owned')
                    try:
                        {'evidence':evidence,'route':route,'proof':proof}[changed].write_bytes(b'changed')
                        self.assertTrue(lock.exists())
                        options['clock']()
                        seen.append('DISPATCH')
                    finally:lock.unlink()
                with patch.object(auto.runtime,'load_bundle',return_value=validated),patch.object(auto.runtime,'audit_runtime_receipts',return_value={'state':{},'revision':0}),patch.object(auto.runtime,'inspect_admission',return_value={'phase':'DAILY_ELIGIBLE_NOT_EXECUTED'}),patch.object(auto.publisher,'run',return_value=published),patch.object(auto.runtime,'run',side_effect=dispatch):
                    with self.assertRaisesRegex(ValueError,'AUTOMATION_ROUTE_.*CHANGED'):auto.run(**args,mode='daily',execute=True)
                self.assertEqual(seen,[]);self.assertEqual(store.path.read_bytes(),before)
                self.assertEqual(len(list((root/'auto-logs').glob('*/failed.json'))),1)

    def test_shared_busy_has_no_dispatch_and_no_failed_attempt(self):
        with TemporaryDirectory() as folder:
            args,_,store=setup(folder);root=Path(folder);lock=root/auto.registrar.LOCK
            lock.parent.mkdir(parents=True,exist_ok=True);lock.write_bytes(b'other')
            before=store.path.read_bytes()
            with patch.object(auto.runtime,'run',side_effect=AssertionError('no dispatch')):
                result=auto.run(**args,mode='daily',execute=True)
            self.assertEqual(result['status'],'LOCK_PRESENT_REVIEW_REQUIRED')
            self.assertEqual(lock.read_bytes(),b'other');self.assertEqual(store.path.read_bytes(),before)
            self.assertEqual(list(root.glob('auto-logs/*/failed.json')),[])

