from copy import deepcopy
import unittest
from test_ndx_dated_batch_summary_20261003 import fixture,m


class Tests(unittest.TestCase):
    def test_all_outcomes_and_bigint_domain(self):
        a=fixture();rows=a['batch']['newly_readback_rows']
        for i,r in enumerate(rows):
            r['attempt_outcome']=m.OUTCOMES[i%4];a['reports_by_id'][r['numerical_task_id']]['attempt_outcome']=r['attempt_outcome']
        a['batch']['new_outcome_counts']={o:sum(r['attempt_outcome']==o for r in rows) for o in m.OUTCOMES}
        out=m.assemble_summary(**a)
        self.assertEqual(sum(out['category_counts'].values()),1632)
        self.assertEqual(out['remaining_without_accepted_terminal_count'],6222659648236111038)
        self.assertEqual(len(out['k_spec_coverage']),51)
        for row in out['k_spec_coverage']:self.assertEqual(sum(row['counts'].values()),32)
        self.assertEqual(out['old_different_cutoff_completed_count_deducted'],0)

    def test_unresolved_dispatch_cannot_be_called_undispatched(self):
        a=fixture(True);b=a['batch'];tid=b['undispatched_task_ids'].pop(0)
        b['unresolved_dispatched_task_ids']=[tid];b['failure']=dict(numerical_task_id=tid,dispatch_invoked=True,reason='DISPATCH_OR_READBACK_FAILURE')
        out=m.assemble_summary(**a);self.assertEqual(out['attempted_task_count'],6)
        for value in (False,0,1,None):
            bad=deepcopy(a);bad['batch']['failure']['dispatch_invoked']=value
            with self.assertRaises(ValueError):m.assemble_summary(**bad)
        bad=deepcopy(a);bad['batch']['undispatched_task_ids'].insert(0,tid);bad['batch']['unresolved_dispatched_task_ids']=[]
        with self.assertRaises(ValueError):m.assemble_summary(**bad)

    def test_cross_report_pointer_source_and_duplicate(self):
        for mutation in (
            lambda a:next(iter(a['reports_by_id'].values()))['source_hashes'].__setitem__(m.READER,'0'*64),
            lambda a:next(iter(a['reports_by_id'].values()))['task_reference'].__setitem__('json_pointer','/materialized/combinations/1/tasks/0'),
            lambda a:a['batch'].__setitem__('new_readback_count',False),
            lambda a:a['batch']['undispatched_task_ids'].append(a['initial']['rows'][0]['numerical_task_id']),
        ):
            a=fixture(True);mutation(a)
            with self.assertRaises(ValueError):m.assemble_summary(**a)

if __name__=='__main__':unittest.main()
