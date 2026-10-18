from copy import deepcopy
import unittest
from unittest.mock import patch
from test_ndx_bulk_lazy_task_materialization_research import fixture,m

class IndependentMaterializerReview(unittest.TestCase):
 def invoke(self,kw,ix):
  with patch.object(m.scheduling,'validate_lazy_plan',return_value=ix):
   return m.materialize_positions(**kw)
 def test_full_matrix_and_suffix_validated_before_unrank(self):
  for attack in ('proposal','unselected','cap','issuer'):
   kw,ix=fixture()
   if attack=='proposal':kw['positions'][-1]['proposal_index']=kw['positions'][0]['proposal_index']
   elif attack=='unselected':kw['panel']['returns'][-1][-1]=True
   elif attack=='cap':kw['max_combinations']=False
   else:kw['panel']['universe'][-1]['issuer_id']='changed-issuer'
   with patch.object(type(ix),'unrank',side_effect=AssertionError('premature unrank')) as unrank:
    with self.assertRaises(ValueError):self.invoke(kw,ix)
    unrank.assert_not_called()
 def test_rehashed_saved_location_and_none_prior_rejected(self):
  for attack in ('location','prior'):
   kw,ix=fixture();row=kw['completed_rebinding']['document']['rows'][0]
   if attack=='location':
    row['new_location_identity']['rank']+=1;row['new_location_id']=m.digest(row['new_location_identity'])
   else:
    n=row['old_completed_row']['full_task']['numerical_identity'];n['requested_previous_target_weights']={};tid=m.digest(n)
    row['numerical_task_id']=row['old_completed_row']['numerical_task_id']=row['old_completed_row']['full_task']['numerical_task_id']=tid
   with self.assertRaises(ValueError):self.invoke(kw,ix)
 def test_complete_reuse_and_matrix_independent_hash(self):
  import hashlib,json
  kw,ix=fixture();before=deepcopy(kw);r=self.invoke(kw,ix);self.assertEqual(kw,before)
  self.assertEqual((r['combination_count'],r['selected_completed_intersection_count'],r['new_unattempted_task_count']),(2,3,3))
  self.assertEqual(r['remaining_full_plan_uncompleted_count'],kw['lazy_plan']['planned_canonical_task_count']-504)
  old={x['numerical_task_id']:x for x in kw['completed_rebinding']['document']['rows']}
  for c in r['combinations']:
   columns=[kw['panel']['columns'].index(t) for t in c['fit_matrix']['tickers']]
   expected={'dates':kw['panel']['dates'],'tickers':c['fit_matrix']['tickers'],'returns':[[row[i] for i in columns] for row in kw['panel']['returns']]}
   self.assertEqual(c['fit_data_sha256'],hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest())
   self.assertEqual(len({t['numerical_task_id'] for t in c['tasks']}),3)
   for t in c['tasks']:
    self.assertIsNone(t['numerical_identity']['requested_previous_target_weights']);self.assertEqual(t['wrapper_call_attempt_count'],0)
    if t['numerical_task_id'] in old:self.assertEqual(t['complete_saved_rebinding_row'],old[t['numerical_task_id']])
    else:self.assertIsNone(t['complete_saved_rebinding_row'])
if __name__=='__main__':unittest.main()
