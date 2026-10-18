import itertools,unittest,copy
from test_bulk_completed_task_rebinding_20261003 import fixture,m
class BulkRebindIndependentReview(unittest.TestCase):
 def test_small_full_rank_order_and_duplicate_issuer(self):
  gs=[dict(issuer_id='a',security_ids=['a0','a1']),dict(issuer_id='b',security_ids=['b0']),dict(issuer_id='c',security_ids=['c0','c1']),dict(issuer_id='d',security_ids=['d0'])]
  lookup={s:g['issuer_id'] for g in gs for s in g['security_ids']}
  for k in range(1,5):
   combos=sorted((tuple(sorted(c,key=lambda s:(lookup[s],s))) for c in itertools.combinations(lookup,k) if len({lookup[s] for s in c})==k))
   for rank,c in enumerate(combos):self.assertEqual(m.prefix_rank(gs,list(c)),rank)
  with self.assertRaises(ValueError):m.prefix_rank([{'issuer_id':'a','security_ids':['a0']},{'issuer_id':'a','security_ids':['a1']}],['a0','a1'])
 def test_timestamp_no_truncation_identity(self):
  d=fixture();panel=d['panel']['panel'];old=d['completed_index']['new_tasks'][0]['full_task']['numerical_identity'];panel['returns']['index'][0]=panel['returns']['index'][0][:10]+'garbageT00:00:00'
  with self.assertRaises(ValueError):m.matrix_and_selected(panel,old)
 def test_full_nested504_zero_attempt_and_reference_preservation(self):
  d=fixture();before=copy.deepcopy(d);out=m.assemble(d);self.assertEqual(d,before)
  self.assertEqual((out['externally_rebound_task_count'],out['externally_rebound_combination_count']),(504,168));self.assertEqual(out['new_fit_count'],0)
  for i,r in enumerate(out['rows']):
   nested=i>=102;position=i-102 if nested else i;key='externally_completed_rebound_rows' if nested else 'new_tasks';original=d['completed_index'][key][position]
   self.assertEqual(r['original_index_row'],original);self.assertEqual(r['prior_rebinding_row'],original if nested else None)
   self.assertEqual(r['original_index_row_reference']['json_pointer'],'/'+key+'/'+str(position));self.assertEqual(r['old_completed_row_reference']['json_pointer'],'/'+key+'/'+str(position)+('/old_completed_row' if nested else ''))
   self.assertEqual(r['new_wrapper_call_attempt_count'],0)
  self.assertEqual(out['full_plan_task_denominator']-out['remaining_uncompleted_task_count'],504)
  d['completed_index']['externally_completed_rebound_rows'][-1]['new_wrapper_call_attempt_count']=False
  with self.assertRaises(ValueError):m.assemble(d)
if __name__=='__main__':unittest.main()
