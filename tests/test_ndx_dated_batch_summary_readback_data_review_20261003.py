from copy import deepcopy
import unittest
from scripts import ndx_dated_batch_summary_independent_readback_20261003 as reader
from test_ndx_dated_batch_summary_20261003 import fixture,m as producer

def case():
    a=fixture(True);ids=[t['numerical_task_id'] for c in a['preparation']['materialized']['combinations'] for t in c['tasks']]
    a['batch']['batch_context']=dict(preparation_reference=a['references']['preparation'],initial_completed_reference=a['references']['initial'],planned_total_task_count=1632,prior_completed_task_count=2,old_cutoff_completion_reused=False,ordered_task_ids_sha256=reader.sha(reader.enc(ids)),source_hashes={a['references']['initial']['path']:a['references']['initial']['sha256'],reader.READER:reader.READER_SHA})
    s=producer.assemble_summary(**a);return s,a
def inspect(s,a):return reader.inspect(s,a['preparation'],a['initial'],a['batch'],a['reports_by_id'])

class Tests(unittest.TestCase):
    def test_stopped_full_partition_and_missing_report(self):
        s,a=case();r=inspect(s,a);self.assertEqual(r['accepted_independent_terminal_count'],5);self.assertEqual(r['undispatched_count'],1627)
        a['reports_by_id'].pop(next(iter(a['reports_by_id'])))
        with self.assertRaises(ValueError):inspect(s,a)
    def test_old_domain_wrong_task_and_boolean_summary_count(self):
        for key,value in [('old_different_cutoff_completed_count_deducted',504),('full_new_cutoff_task_denominator',2136),('old_different_cutoff_completed_count_deducted',False)]:
            s,a=case();s[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):inspect(s,a)
        s,a=case();s['rows'][0]['task_reference']['json_pointer']='/materialized/combinations/1/tasks/0'
        with self.assertRaises(ValueError):inspect(s,a)
    def test_report_contract_not_just_copied_metadata(self):
        for key,value in [('point_in_time_verified',0),('schema','OTHER_READER'),('materialized_task_denominator',True),('source_hashes',{})]:
            s,a=case();tid=s['rows'][0]['numerical_task_id'];a['reports_by_id'][tid][key]=value;s['rows'][0]['independent_report_preserved']=deepcopy(a['reports_by_id'][tid])
            with self.subTest(key=key),self.assertRaises(ValueError):inspect(s,a)
    def test_batch_counts_failure_and_initial_copy(self):
        for change in ('boolcount','finished','initialcopy','outcome'):
            s,a=case()
            if change=='boolcount':a['batch']['new_readback_count']=True
            elif change=='finished':a['batch']['status']='BUDGETED_QUEUE_FINISHED'
            elif change=='initialcopy':a['batch']['initial_completed_rows']=[]
            else:
                a['batch']['newly_readback_rows'][0]['attempt_outcome']='VALIDATION_FAILURE';s['rows'][2]['saved_batch_row']=deepcopy(a['batch']['newly_readback_rows'][0])
            with self.subTest(change=change),self.assertRaises(ValueError):inspect(s,a)
    def test_batch_context_must_match_independently_derived_order(self):
        for key,value in [('ordered_task_ids_sha256','a'*64),('prior_completed_task_count',504),('old_cutoff_completion_reused',0)]:
            s,a=case();a['batch']['batch_context'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):inspect(s,a)

if __name__=='__main__':unittest.main()
