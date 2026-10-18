from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_dated_comparison_results_summary_20261003 as m
from backtest import ndx_dated_comparison_results_summary_research as core
from test_ndx_dated_comparison_results_summary_research import fixture,saved

class Tests(unittest.TestCase):
    def test_stream_projection_exactly_matches_frozen_pure(self):
        a=fixture()
        for i in (0,1,2):
            task=a['task_summary']['rows'][i];a['comparisons_by_task'][task['numerical_task_id']]=saved(task,first=i==0,missing=i==1,decision='NO_PLAN' if i==2 else 'FROZEN',execution=None if i==2 else 'REJECTED')
        expected=core.summarize_comparisons(**a);calls=[]
        def load(tid,refs):calls.append(tid);return deepcopy(a['comparisons_by_task'][tid])
        output=m.stream_summary(a['task_summary'],a['task_summary_reference'],dict.fromkeys(a['comparisons_by_task'],{}),load,core)
        self.assertEqual(output,expected);self.assertEqual(calls,[t['numerical_task_id'] for t in a['task_summary']['rows'][:3]]);self.assertEqual(output['not_supplied_count'],1629)
        self.assertNotIn('original_account_preserved',output['rows'][0]['tracks']['candidate_integer'])
    def test_pending_never_reads_or_dispatches(self):
        with self.assertRaises(ValueError):m.run()
        with patch.dict(m.BOUND,{'batch':('pending',None)}),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.run(execute=True)
            read.assert_not_called()
    def test_partial_batch_does_not_drop_missing_denominator(self):
        from test_ndx_dated_comparison_batch_20261003 import fixture as batchfixture
        a=batchfixture();summary=a['summary'];initial=a['initial'];newid=summary['rows'][3]['numerical_task_id'];r=dict(path='x',sha256='a'*64)
        batch=dict(schema='DATED_COMPARISON_BATCH_RESULT_V1',initial_rows_preserved=initial['rows'],planned_remaining_count=1629,new_completed_count=1,new_completed_rows=[dict(numerical_task_id=newid,stage_references=dict(comparison=r,independent_readback=r))],unresolved_task_ids=[],undispatched_task_ids=[t['numerical_task_id'] for t in summary['rows'][4:]],status='STOPPED_WITH_EVIDENCE',failure=dict(numerical_task_id=summary['rows'][4]['numerical_task_id'],stage_may_have_written_evidence=False))
        self.assertEqual(len(m.index_comparisons(summary,initial,batch)),4)
        batch['undispatched_task_ids'].pop()
        with self.assertRaises(ValueError):m.index_comparisons(summary,initial,batch)
    def test_failure_after_publication_retained_and_no_retry(self):
        docs=dict(task_summary={},batch=dict(failure=None,unresolved_task_ids=[],undispatched_task_ids=[]));count=[0]
        def guard(s):
            count[0]+=1
            if count[0]==3:raise ValueError('Changed base after receipt')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'output'
            with patch.object(m,'OUTPUT',out),patch.object(m,'load_inputs',return_value=(docs,{}, {},object())),patch.object(m,'stream_summary',return_value={}),patch.object(m,'guard',side_effect=guard):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertTrue((out/'summary.json').exists());self.assertTrue((out/'publication.json').exists());self.assertTrue((out/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)
    def test_bad_item_refs_not_silently_dropped(self):
        a=fixture();task=a['task_summary']['rows'][1];e=saved(task);e['audit']['comparison_reference']['sha256']='f'*64
        with self.assertRaises(ValueError):m.stream_summary(a['task_summary'],a['task_summary_reference'],{task['numerical_task_id']:{}},lambda *args:e,core)
if __name__=='__main__':unittest.main()
