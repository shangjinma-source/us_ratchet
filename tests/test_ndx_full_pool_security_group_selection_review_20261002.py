import copy,unittest
from test_ndx_full_pool_security_group_selection_20261002 import fixture,m
class SelectionIndependentReview(unittest.TestCase):
 def test_integer_flags_and_counts_do_not_alias(self):
  for mutate in (lambda r,q,d:r['supporting_evidence'].update(early_window_review_availability_verified=0),lambda r,q,d:r['supporting_evidence'].update(review_selection_postdates_window_start=1),lambda r,q,d:d['extraction']['dei_facts'][0].update(context_match_count=True)):
   args=fixture();mutate(*args[:3])
   with self.assertRaises(ValueError):m.validate_selection(*args)
 def test_duplicate_context_and_incomplete_ticker_block(self):
  for kind in ['duplicate','empty','bool']:
   r,q,d,ref=fixture()
   if kind=='duplicate':d['extraction']['contexts'].append(copy.deepcopy(d['extraction']['contexts'][0]))
   else:
    d['extraction']['same_context_security_groups'][0]['ticker_fact_indexes']=[] if kind=='empty' else [True]
    r['all_security_groups']=copy.deepcopy(d['extraction']['same_context_security_groups'])
   with self.assertRaises(ValueError):m.validate_selection(r,q,d,ref)
 def test_original_evidence_and_alternatives_no_mutation(self):
  args=fixture();original=copy.deepcopy(args);out=m.validate_selection(*args)
  self.assertEqual(args,original);self.assertEqual(out,args[0]);self.assertFalse(out['supporting_evidence']['early_window_review_availability_verified'])
  args[2]['extraction']['same_context_security_groups'].append({'context_ref':'bond','title_fact_indexes':[2],'ticker_fact_indexes':[3]})
  with self.assertRaises(ValueError):m.validate_selection(*args)
if __name__=='__main__':unittest.main()
