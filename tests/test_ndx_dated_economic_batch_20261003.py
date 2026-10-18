"""Synthetic orchestration only; no fitting, producer imports or actual accounts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
p=Path(__file__).resolve().parents[1]/'scripts/ndx_dated_economic_batch_20261003.py';s=importlib.util.spec_from_file_location('driver',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
    def test_six_stages_exact_order_no_control(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'batch'
            def make(stage):
                def call(tid,refs):
                    self.assertEqual(list(refs),list(m.STAGES[:m.STAGES.index(stage)]));calls.append((tid,stage));return dict(path=stage,sha256='a'*64)
                return call
            result=m.execute_queue(['a'*64,'b'*64],initial_rows=[{'preserved':'old'}],stage_functions={k:make(k) for k in m.STAGES},verify_sources=lambda:None,output=output)
            saved=json.loads(Path(result['path']).read_bytes());self.assertEqual(saved['new_completed_count'],2);self.assertEqual(calls,[(tid,k) for tid in ('a'*64,'b'*64) for k in m.STAGES]);self.assertFalse(saved['incumbent_executed'])
            with self.assertRaises(ValueError):m.execute_queue([],initial_rows=[],stage_functions={k:make(k) for k in m.STAGES},verify_sources=lambda:None,output=output)
    def test_failure_retains_returned_audit_before_validation(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            def call(tid,refs):calls.append(tid);return dict(path='saved',sha256='b'*64)
            def validate(tid,stage,ref,refs):
                if stage=='account_readback':raise ValueError('technical account failure')
            ref=m.execute_queue(['a'*64,'b'*64],initial_rows=[],stage_functions=dict.fromkeys(m.STAGES,call),verify_sources=lambda:None,validate_stage=validate,output=Path(tmp)/'batch')
            doc=json.loads(Path(ref['path']).read_bytes());self.assertEqual(len(calls),4);self.assertIn('account_readback',doc['failure']['completed_stage_references']);self.assertEqual(doc['undispatched_task_ids'],['b'*64]);self.assertEqual(doc['unresolved_task_ids'],['a'*64]);self.assertFalse(doc['retry_allowed'])
    def test_exception_never_continues_or_retries(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            def call(tid,refs):calls.append(tid);raise RuntimeError('source changed after partial output')
            ref=m.execute_queue(['a'*64,'b'*64],initial_rows=[],stage_functions=dict.fromkeys(m.STAGES,call),verify_sources=lambda:None,output=Path(tmp)/'batch')
            value=json.loads(Path(ref['path']).read_bytes());self.assertEqual(calls,['a'*64]);self.assertEqual(value['failure']['stage'],'inputs');self.assertTrue(value['failure']['stage_may_have_written_evidence'])
    def test_resource_stop_keeps_current_task_undispatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            def forbidden(*args):raise AssertionError('must not dispatch')
            ref=m.execute_queue(['a'*64,'b'*64],initial_rows=[],stage_functions=dict.fromkeys(m.STAGES,forbidden),verify_sources=lambda:None,resource_check=lambda:m.MIN_FREE_BYTES-1,output=Path(tmp)/'batch')
            doc=json.loads(Path(ref['path']).read_bytes());self.assertEqual(doc['failure']['reason'],'RESOURCE_STOP_BEFORE_DISPATCH');self.assertEqual(doc['undispatched_task_ids'],['a'*64,'b'*64]);self.assertEqual(doc['unresolved_task_ids'],[])
    def test_pending_and_explicit_no_sideeffects(self):
        with self.assertRaises(ValueError):m.run()
        with patch.dict(m.BOUND, {'summary':dict(path='pending',sha256=None)}):
            with self.assertRaises(ValueError):m.run(execute=True)
        for relative,digest in m.PINS.values():
            if digest is not None:self.assertEqual(m.sha((m.ROOT/relative).read_bytes()),digest)
    def test_real_saved_metadata_preflight_no_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            # Recreate the historical three-task directory inventory; metadata stays real.
            inputs=root/'inputs';accounts=root/'accounts';continuous=root/'continuous'
            for folder,ids in ((inputs,m.INITIAL_IDS),(accounts,m.INITIAL_IDS),(continuous,m.INITIAL_IDS-{m.FIRST})):
                folder.mkdir()
                for task_id in ids:(folder/task_id).mkdir()
            with patch.object(m,'OUTPUT',root/'uncreated-batch'),patch.object(m,'INPUT_ROOT',inputs),patch.object(m,'ACCOUNT_ROOT',accounts),patch.object(m,'CONTINUOUS_ROOT',continuous),patch.object(m,'load_module',side_effect=AssertionError('No execution import')),patch.object(m,'execute_queue',side_effect=AssertionError('No dispatch')):
                checked=m.preflight()
                self.assertFalse(m.OUTPUT.exists())
                (inputs/'unexpected').mkdir()
                with self.assertRaisesRegex(ValueError,'Only explicitly audited existing task namespaces'):m.preflight()
        self.assertEqual(len(checked['order']),1632);self.assertEqual(len(checked['initial']['rows']),3)
    def test_initial_exact_three_and_original_order(self):
        ids=sorted(m.INITIAL_IDS)+[format(i,'064x') for i in range(1629)]
        rows=[dict(numerical_task_id=tid,category='RISK_FAILED',saved_batch_row={'independent_readback_reference':dict(path=tid,sha256='a'*64)}) for tid in ids]
        summary=dict(schema='DATED_BATCH_SAVED_READBACK_SUMMARY_V1',rows=rows,full_new_cutoff_task_denominator=m.FULL,old_different_cutoff_completed_count_deducted=0)
        initial=dict(schema='DATED_INITIAL_ECONOMIC_COMPLETED_V1',preparation_reference=m.PREPARATION_REFERENCE,rows=[dict(numerical_task_id=tid,**{k:dict(path=k,sha256='b'*64) for k in (*m.STAGES,'inputs_publication','continuous_publication')}) for tid in sorted(m.INITIAL_IDS)])
        self.assertEqual(m.validate_queue(summary,initial),ids)
        initial['rows'][1]=initial['rows'][0]
        with self.assertRaises(ValueError):m.validate_queue(summary,initial)
if __name__=='__main__':unittest.main()
