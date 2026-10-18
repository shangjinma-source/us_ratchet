from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from scripts import ndx_dated_comparison_batch_20261003 as m

def fixture():
    ids=sorted(m.INITIAL_IDS)+[format(i,'064x') for i in range(1629)]
    ref=lambda k:dict(path=k,sha256='a'*64)
    initial_econ=dict(schema='DATED_INITIAL_ECONOMIC_COMPLETED_V1',preparation_reference=m.PREPARATION_REFERENCE,rows=[dict(numerical_task_id=tid,**{k:ref(k) for k in (*m.ECONOMIC_STAGES,'inputs_publication','continuous_publication')}) for tid in ids[:3]])
    economic=dict(schema='DATED_ECONOMIC_BATCH_RESULT_V1',initial_rows_preserved=deepcopy(initial_econ['rows']),status='REQUESTED_ECONOMIC_STAGES_FINISHED',failure=None,unresolved_task_ids=[],undispatched_task_ids=[],planned_remaining_count=1629,new_completed_count=1629,new_completed_rows=[dict(numerical_task_id=tid,stage_references={k:ref(k) for k in m.ECONOMIC_STAGES}) for tid in ids[3:]])
    initial=dict(schema='DATED_INITIAL_COMPARISONS_V1',preparation_reference=m.PREPARATION_REFERENCE,rows=[dict(numerical_task_id=tid,comparison_reference=ref(tid),publication_reference=ref(tid+'pub'),independent_readback_reference=ref(tid+'audit')) for tid in ids[:3]])
    summary=dict(schema='DATED_BATCH_SAVED_READBACK_SUMMARY_V1',rows=[dict(numerical_task_id=tid) for tid in ids],full_new_cutoff_task_denominator=m.FULL)
    return dict(summary=summary,economic_initial=initial_econ,economic_result=economic,initial=initial)
class Tests(unittest.TestCase):
    def test_full_order_reuses_only_explicit_three(self):
        a=fixture();ids,refs=m.validate_queue(**a);self.assertEqual(len(ids),1632);self.assertEqual(len(refs),1632);self.assertEqual(len([t for t in ids if t not in m.INITIAL_IDS]),1629)
    def test_incomplete_or_changed_stages_never_shortened(self):
        for mutate in (lambda a:a['economic_result'].update(status='STOPPED_WITH_EVIDENCE',undispatched_task_ids=['x']),lambda a:a['economic_result'].update(new_completed_count=True),lambda a:a['economic_result']['new_completed_rows'][0]['stage_references'].pop('account_readback'),lambda a:a['economic_result']['new_completed_rows'].reverse()):
            a=fixture();mutate(a)
            with self.assertRaises(ValueError):m.validate_queue(**a)
    def test_both_stages_each_once_and_result_reference_failure_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def producer(tid,refs):calls.append('producer');return dict(path='comparison',sha256='a'*64)
            def reader(tid,refs):calls.append('reader');return dict(path='audit',sha256='b'*64)
            def validate(tid,stage,ref,refs):
                if stage=='independent_readback':raise ValueError('audit failed')
            ref=m.execute_queue(['a'*64,'b'*64],initial_rows=[],stage_functions=dict(comparison=producer,independent_readback=reader),verify_sources=lambda:None,validate_stage=validate,output=Path(tmp)/'batch')
            doc=json.loads(Path(ref['path']).read_bytes());self.assertEqual(calls,['producer','reader']);self.assertIn('independent_readback',doc['failure']['completed_stage_references']);self.assertEqual(doc['unresolved_task_ids'],['a'*64]);self.assertEqual(doc['undispatched_task_ids'],['b'*64])
    def test_pre_dispatch_resource_and_source_failure(self):
        for resource in (lambda:0,lambda:(_ for _ in ()).throw(OSError('disk unavailable'))):
            with tempfile.TemporaryDirectory() as tmp:
                def forbidden(*args):raise AssertionError('No dispatch')
                ref=m.execute_queue(['a'*64],initial_rows=[],stage_functions=dict.fromkeys(m.STAGES,forbidden),verify_sources=lambda:None,resource_check=resource,output=Path(tmp)/'batch')
                doc=json.loads(Path(ref['path']).read_bytes());self.assertEqual(doc['undispatched_task_ids'],['a'*64]);self.assertEqual(doc['unresolved_task_ids'],[]);self.assertFalse(doc['failure']['stage_may_have_written_evidence'])
    def test_retry_pending_and_source_pins(self):
        with self.assertRaises(ValueError):m.run()
        with patch.dict(m.BOUND, {'economic_result':dict(path='pending-result.json',sha256=None)}):
            with self.assertRaises(ValueError):m.run(execute=True)
        for relative,h in m.PINS.values():
            if h:self.assertEqual(m.sha((m.ROOT/relative).read_bytes()),h)
        for ref in m.BOUND.values():
            if ref['sha256']:self.assertEqual(m.sha(Path(ref['path']).read_bytes()),ref['sha256'])
    def test_source_guard_after_first_stage_retains_prefix(self):
        n=[0]
        def guard():
            n[0]+=1
            if n[0]==3:raise ValueError('Changed source')
        with tempfile.TemporaryDirectory() as tmp:
            call=lambda tid,refs:dict(path='saved',sha256='a'*64)
            out=Path(tmp)/'batch';ref=m.execute_queue(['a'*64],initial_rows=[],stage_functions=dict.fromkeys(m.STAGES,call),verify_sources=guard,output=out)
            self.assertEqual(json.loads(Path(ref['path']).read_bytes())['failure']['completed_stage_references'],{'comparison':dict(path='saved',sha256='a'*64)})
            with self.assertRaises(ValueError):m.execute_queue([],initial_rows=[],stage_functions=dict.fromkeys(m.STAGES,call),verify_sources=lambda:None,output=out)
if __name__=='__main__':unittest.main()
