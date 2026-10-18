from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import unittest
from scripts import ndx_dated_comparison_batch_independent_readback_20261003 as m
from test_ndx_dated_comparison_batch_20261003 import fixture as source_fixture

def fixture():
    a=source_fixture();a['summary']['old_different_cutoff_completed_count_deducted']=0
    ids=[r['numerical_task_id'] for r in a['summary']['rows']];remaining=ids[3:]
    context=dict(full_task_count=1632,full_new_cutoff_task_denominator=m.FULL,input_references={k:m.ref(k) for k in ('summary','economic_initial','economic_result','economic_audit','initial')},source_hashes={m.ref(k)['path']:m.ref(k)['sha256'] for k in m.BOUND},resource_gate_does_not_reduce_domain=True,minimum_free_disk_bytes=5*1024**3,**dict.fromkeys(m.BATCH_FALSE,False))
    batch=dict(schema='DATED_COMPARISON_BATCH_RESULT_V1',status='REQUESTED_COMPARISONS_FINISHED',context=context,initial_rows_preserved=deepcopy(a['initial']['rows']),new_completed_rows=[dict(numerical_task_id=t,stage_references={k:dict(path=t+k,sha256='a'*64) for k in m.STAGES}) for t in remaining],planned_remaining_count=1629,new_completed_count=1629,unresolved_task_ids=[],undispatched_task_ids=[],failure=None,**dict.fromkeys(m.BATCH_FALSE,False))
    return a,batch

class Tests(unittest.TestCase):
    def test_complete_order_and_parent_roles(self):
        a,b=fixture();ids,new,f=m.partition(a['summary'],a['initial'],b);self.assertEqual(len(new),1629);self.assertIsNone(f)
        self.assertEqual(len(m.economic_map(ids,a['economic_initial'],a['economic_result'])),1632)
    def test_before_and_after_dispatch_stopped_partition(self):
        for invoked in (False,True):
            a,b=fixture();remaining=[r['numerical_task_id'] for r in b['new_completed_rows']];b.update(status='STOPPED_WITH_EVIDENCE',new_completed_rows=[],new_completed_count=0,unresolved_task_ids=remaining[:1] if invoked else [],undispatched_task_ids=remaining[1:] if invoked else remaining,failure=dict(ordinal=0,numerical_task_id=remaining[0],task_stage_invoked=invoked,current_stage_invoked=invoked,stage_may_have_written_evidence=invoked,retry_allowed=False,completed_stage_references={},stage='comparison' if invoked else None))
            self.assertIsNotNone(m.partition(a['summary'],a['initial'],b)[2])
            bad=deepcopy(b);bad['failure']['task_stage_invoked']=int(invoked)
            with self.assertRaises(ValueError):m.partition(a['summary'],a['initial'],bad)
    def test_bool_omission_wrong_context_and_duplicate_reject(self):
        for mutate in (lambda a,b:b.update(new_completed_count=True),lambda a,b:b['new_completed_rows'].pop(),lambda a,b:b['context'].update(full_task_count=2136),lambda a,b:b['new_completed_rows'].reverse(),lambda a,b:a['summary'].update(old_different_cutoff_completed_count_deducted=504)):
            a,b=fixture();mutate(a,b)
            with self.assertRaises(ValueError):m.partition(a['summary'],a['initial'],b)
    def test_pending_no_io(self):
        with patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.readback(dict(path='x',sha256='a'*64),execute=True)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
