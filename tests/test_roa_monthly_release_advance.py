import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts.research.advance_roa_monthly_release import advance


class AdvanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        def save(name,value):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            raw=json.dumps(value).encode();path.write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        self.save=save
        active=save('active.json',{'release':'old'})
        receipt=save('receipt.json',dict(status='PREPARED_VERIFIED_NOT_REGISTERED',month='2026-12',runtime_sha256='artifact'))
        registration=save('registration.json',dict(expected_active=active,month='2026-12',receipt=receipt))
        publication=save('publication.json',dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED',expected_active=active,registration=registration,month='2026-12'))
        self.request=dict(active=active,registration=registration,publication=publication,month='2026-12',epoch='epoch',expected_process={'pid':1})
        self.adoptions=0;self.finishes=0;self.healthy=True
        self.adapter=lambda *a,**kw:SimpleNamespace(inspect=lambda:dict(healthy=self.healthy,active_sha256='new',process_identity={'pid':2}),get_json=lambda _: {},restart=lambda **kw:None)
    def adopt(self,**kw):
        self.adoptions+=1
        active=self.save('active.json',{'release':'new'})
        self.save('tmp/attempt/adoption/adoption.json',dict(status='ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED',expected_active=self.request['active'],registration=self.request['registration'],active_sha256=active['sha256']))
    def finish(self,**kw):
        self.finishes+=1
        return dict(status='MONTH_RUNTIME_VERIFIED')
    def run_it(self,execute=True,finish=None,adopt=None):
        with patch('scripts.research.advance_roa_monthly_release.adopt',side_effect=adopt or self.adopt),patch('scripts.research.advance_roa_monthly_release.finish',side_effect=finish or self.finish):
            return advance(root=self.root,request=self.request,output_directory='tmp/attempt',execute=execute,adapter_factory=self.adapter)
    def test_preview_has_no_outputs(self):
        self.assertEqual(self.run_it(False)['status'],'PREVIEW_NO_ADOPTION_OR_RESTART')
        self.assertFalse((self.root/'tmp').exists());self.assertEqual(self.adoptions,0)
    def test_resume_does_not_repeat_adoption(self):
        self.run_it();self.run_it()
        self.assertEqual(self.adoptions,1);self.assertEqual(self.finishes,2)
    def test_lost_adoption_acknowledgment_reuses_receipt(self):
        def lost(**kw):self.adopt(**kw);raise TimeoutError()
        with self.assertRaises(TimeoutError):self.run_it(adopt=lost)
        self.run_it();self.assertEqual(self.adoptions,1)
    def test_unresolved_switch_never_repeats(self):
        with self.assertRaises(TimeoutError):self.run_it(adopt=lambda **kw:(_ for _ in ()).throw(TimeoutError()))
        with self.assertRaisesRegex(ValueError,'INTENT_UNRESOLVED'):self.run_it()
        self.assertEqual(self.adoptions,0)
    def test_startup_wait_does_not_repeat_finish_or_restart(self):
        def pending(**kw):
            self.save('tmp/attempt/runtime/restart-intent.json',{})
            self.healthy=False
            raise ValueError('RESTARTED_RUNTIME_NOT_VERIFIED')
        with self.assertRaisesRegex(ValueError,'NOT_VERIFIED'):self.run_it(finish=pending)
        result=self.run_it()
        self.assertEqual(result['status'],'WAIT_RUNTIME_RECONCILIATION_NO_REPEAT_RESTART')
        self.assertEqual(self.adoptions,1);self.assertEqual(self.finishes,0)
    def test_later_active_not_overwritten(self):
        self.run_it();self.save('active.json',{'release':'later'})
        with self.assertRaisesRegex(ValueError,'RECONCILIATION_REQUIRED'):self.run_it()
        self.assertEqual(self.adoptions,1)
    def test_successor_receives_actual_adopted_receipts(self):
        self.request['successor']=dict(inputs={'manifest':{'path':'fixture'}},python_path='python',expected_task_sha256='old-task')
        def finished(**kw):
            self.save('tmp/attempt/runtime/success.json',{'status':'MONTH_RUNTIME_VERIFIED'})
            self.save('tmp/attempt/adoption/validated.json',{'month':'2026-12'})
            return {'status':'MONTH_RUNTIME_VERIFIED'}
        def next_month(**kw):
            inputs=kw['request']
            self.assertEqual(inputs['active']['sha256'],sha256((self.root/'active.json').read_bytes()).hexdigest())
            self.assertEqual(inputs['publication']['path'],'tmp/attempt/adoption/validated.json')
            self.assertEqual(inputs['runtime_success']['path'],'tmp/attempt/runtime/success.json')
            self.assertEqual(kw['expected_task_sha256'],'old-task')
            return {'status':'NEXT_MONTH_TASK_BOUND','target_month':'2027-01'}
        with patch('scripts.research.advance_roa_monthly_release.finish_next',side_effect=next_month) as called:
            result=self.run_it(finish=finished)
        self.assertEqual(result['status'],'MONTH_RUNTIME_AND_NEXT_TASK_VERIFIED')
        self.assertEqual(called.call_count,1)

if __name__=='__main__':unittest.main()
