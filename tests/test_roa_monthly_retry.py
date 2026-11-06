import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts.prepare_roa_monthly_retry import prepare_retry

class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        def write(name,value):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
            raw=json.dumps(value).encode();p.write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        self.write=write
        active=write('active.json',{})
        plan=write('plan.json',dict(output_directory='tmp/old/capture',session='2026-11-30'))
        request=write('request.json',dict(active=active,capture=dict(plan=plan,output_directory='tmp/old/training'),package=dict(expected_month='2026-12'),coordination_directory='tmp/old/coordination',publication_directory='tmp/old/publication'))
        self.descriptor=write('launcher.json',dict(request=request,log_directory='tmp/old/logs',python_path='python'))
        self.failure=write('tmp/old/logs/blocked.json',dict(descriptor_sha256=self.descriptor['sha256'],error='TRANSIENT_FETCH'))
        self.arguments=dict(root=self.root,descriptor=self.descriptor,failure=self.failure,output_directory='tmp/new',reason='Reviewed transient fetch failure')
        self.guard=patch('scripts.prepare_roa_monthly_retry.run',return_value={'status':'PREVIEW_VALIDATED_NO_CAPTURE'}).start();self.addCleanup(patch.stopall)
        patch('scripts.prepare_roa_monthly_retry.make_descriptor',side_effect=lambda **kw:dict(request=kw['request'],log_directory=kw['log_directory'])).start()
    def test_new_attempt_preserves_failure_and_redirects_all_outputs(self):
        before=(self.root/self.failure['path']).read_bytes()
        result=prepare_retry(**self.arguments,prepare=True)
        self.assertEqual(result['status'],'NEW_ATTEMPT_PREPARED_NOT_SCHEDULED')
        self.assertEqual((self.root/self.failure['path']).read_bytes(),before)
        request=json.loads((self.root/'tmp/new/request.json').read_bytes());plan=json.loads((self.root/'tmp/new/capture_plan.json').read_bytes())
        self.assertEqual(plan['output_directory'],'tmp/new/capture')
        self.assertEqual(request['capture']['output_directory'],'tmp/new/training')
        self.assertEqual(request['coordination_directory'],'tmp/new/coordination')
        self.assertTrue(all(call.kwargs['execute'] is False for call in self.guard.call_args_list))
    def test_preview_writes_nothing(self):
        self.assertEqual(prepare_retry(**self.arguments)['status'],'NEW_ATTEMPT_PREVIEW')
        self.assertFalse((self.root/'tmp/new').exists())
    def test_existing_lock_not_deleted(self):
        lock=self.root/'tmp/old/logs/running.lock';lock.write_text('token')
        with self.assertRaisesRegex(ValueError,'LOCK_RECONCILIATION'):prepare_retry(**self.arguments,prepare=True)
        self.assertEqual(lock.read_text(),'token');self.assertFalse((self.root/'tmp/new').exists())
    def test_active_changed_rejected(self):
        self.write('active.json',dict(changed=True))
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):prepare_retry(**self.arguments,prepare=True)
    def test_wrong_failure_rejected(self):
        self.arguments['failure']=self.write('other/blocked.json',dict(descriptor_sha256=self.descriptor['sha256']))
        with self.assertRaisesRegex(ValueError,'FAILURE_NOT_FROM'):prepare_retry(**self.arguments)
    def test_existing_output_not_overwritten(self):
        (self.root/'tmp/new').mkdir()
        with self.assertRaisesRegex(ValueError,'MUST_NOT_EXIST'):prepare_retry(**self.arguments,prepare=True)
    def test_nested_old_output_refused(self):
        self.arguments['output_directory']='tmp/old/capture/retry'
        with self.assertRaisesRegex(ValueError,'OVERLAPS_OLD'):prepare_retry(**self.arguments,prepare=True)

if __name__=='__main__':unittest.main()
