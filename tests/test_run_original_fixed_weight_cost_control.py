import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts import run_original_fixed_weight_cost_control as m


class OnceRunnerTests(unittest.TestCase):
    def fixture(self,root,authorized=False):
        pins={}
        for n in ['scripts/run_original_fixed_weight_cost_control.py','backtest/original_fixed_weight_cost_next_open.py','scripts/compare_monthly_latched_exit.py']:
            p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture');pins[n]=sha256(b'fixture').hexdigest()
        bundle=dict(source_hashes=pins,initial_cash='20000',weights={'A':'1'},scenarios=m.SCENARIOS,assembled=dict(session_dates=['2024-01-02','2024-01-03'],monthly_inputs=[{'search_arguments':{'fee_bps':'0'}}]),ohlc={})
        bundle['assembled']['original_control_action_scope']={'active_policy':'SEALED_FULL_DOMAIN'}
        baseline=root/m.BASE;baseline.parent.mkdir(parents=True,exist_ok=True);baseline.write_bytes(b'{}');pins[m.BASE]=sha256(b'{}').hexdigest()
        raw=json.dumps(bundle).encode();(root/'inputs.json').write_bytes(raw)
        c=dict(event_scope='SEALED_FULL_DOMAIN',inputs_path='inputs.json',inputs_sha256=sha256(raw).hexdigest(),new_source_hashes=pins,initial_cash='20000',weights={'A':'1'},scenarios=m.SCENARIOS,total_maximum_books=2,maximum_search_calls=0,automatic_retry=False,output_directory=m.OUTPUT,execution_authorized=authorized)
        raw=json.dumps(c).encode();p=root/'contract.json';p.write_bytes(raw)
        return dict(contract_path=p,contract_sha256=sha256(raw).hexdigest())

    def test_readonly_and_unauthorized_no_output(self):
        with TemporaryDirectory() as folder,patch.object(m,'ROOT',Path(folder)):
            args=self.fixture(Path(folder))
            with patch.object(m,'run_original_fixed_weight_next_open',side_effect=AssertionError('no book')):
                self.assertEqual(m.run(**args)['status'],'PREFLIGHT_ONLY_NO_BOOK')
                with self.assertRaisesRegex(ValueError,'RUN_REGISTRATION'):m.run(**args,execute=True)
            self.assertFalse((Path(folder)/m.OUTPUT).exists())

    def test_two_isolated_cost_arms_and_create_only(self):
        with TemporaryDirectory() as folder,patch.object(m,'ROOT',Path(folder)):
            args=self.fixture(Path(folder),True);calls=[]
            def book(**kwargs):
                calls.append(kwargs)
                self.assertNotIn('mutated',kwargs['assembled'])
                self.assertEqual(kwargs['initial_cash'],'20000')
                self.assertEqual(kwargs['assembled']['monthly_inputs'][0]['search_arguments']['fee_bps'],kwargs['fee_bps'])
                kwargs['assembled']['mutated']=True
                return {'status':'COMPLETE'}
            with patch.object(m,'run_original_fixed_weight_next_open',side_effect=book),patch.object(m,'statistics',return_value={}):
                self.assertEqual(m.run(**args,execute=True)['book_calls'],2)
                with self.assertRaises(FileExistsError):m.run(**args,execute=True)
            self.assertEqual([x['fee_bps'] for x in calls],['0','1'])

    def test_filtered_event_payload_cannot_be_registered_as_full(self):
        with TemporaryDirectory() as folder,patch.object(m,'ROOT',Path(folder)):
            root=Path(folder);args=self.fixture(root)
            inputs=json.loads((root/'inputs.json').read_bytes());inputs['assembled']['actions']=[]
            raw=json.dumps(inputs).encode();(root/'inputs.json').write_bytes(raw)
            contract=json.loads((root/'contract.json').read_bytes());contract['inputs_sha256']=sha256(raw).hexdigest()
            raw=json.dumps(contract).encode();(root/'contract.json').write_bytes(raw);args['contract_sha256']=sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,'SEALED_EVENT_INPUT_MISMATCH'):m.run(**args)

    def test_drift_and_failure_preserve_no_retry(self):
        with TemporaryDirectory() as folder,patch.object(m,'ROOT',Path(folder)):
            root=Path(folder);args=self.fixture(root,True)
            with patch.object(m,'run_original_fixed_weight_next_open',side_effect=ValueError('failure')):
                with self.assertRaises(ValueError):m.run(**args,execute=True)
            self.assertTrue((root/m.OUTPUT/'failed.json').exists())
            with self.assertRaises(FileExistsError):m.run(**args,execute=True)
            (root/'backtest/original_fixed_weight_cost_next_open.py').write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT'):m.run(**args)


if __name__=='__main__':unittest.main()
