import copy,unittest
from test_ndx_bulk_conditional_wiring_20261003 import fixture,module
class BulkIndependentReview(unittest.TestCase):
 def test_cross_context_preserves_dimensions_but_requires_equal_period(self):
  a=fixture();c=a[1]['links'][0]['link']['all_cik_links'][0]
  c['relation']='CROSS_CONTEXT_EQUAL_IDENTIFIERS_AND_PERIODS_CONDITIONAL_LINK'
  c['cik_contexts']=copy.deepcopy(c['cik_contexts']);c['cik_contexts'][0]['context_id']='entity';c['cik_contexts'][0]['dimensions']=[{'entity':'old'}];c['cik_fact']['context_ref']='entity'
  original=copy.deepcopy(a);result=module.assemble_bulk_conditional_wiring(*a)
  self.assertEqual(a,original);self.assertEqual(result['bulk_extended_provenance'][0]['selected_matching_cik_links'],[c])
  c['cik_contexts'][0]['periods']=[{'value':'different'}]
  with self.assertRaises(ValueError):module.assemble_bulk_conditional_wiring(*a)
 def test_historical_and_late_claims_not_trusted(self):
  a=fixture();a[1]['historical_denominators'].pop()
  with self.assertRaises(ValueError):module.assemble_bulk_conditional_wiring(*a)
  a=fixture();link=a[1]['links'][0]['link'];link['original_queue_item']['review_match']['decision']['selection_date']='2025-01-01';link['saved_review_date_fields']['selection_date']['value']='2025-01-01'
  with self.assertRaises(ValueError):module.assemble_bulk_conditional_wiring(*a)
 def test_all_old_rows_and_bad_cik_alternatives_preserved(self):
  a=fixture();link=a[1]['links'][0]['link'];bad=copy.deepcopy(link['all_cik_links'][0]);bad.update(cik_matches_review_issuer=False,cik_review_issuer_match_status='MISMATCH');bad['normalized_cik']='9999999999';bad['cik_fact']['resolved_text']='9999999999';link['all_cik_links'].insert(0,bad)
  out=module.assemble_bulk_conditional_wiring(*a)
  self.assertEqual(out['nonmatching_cik_link_count_preserved'],1)
  self.assertEqual(out['bulk_extended_provenance'][0]['complete_link_row'],a[1]['links'][0])
  self.assertEqual(len(out['bulk_extended_provenance'][0]['selected_matching_cik_links']),1)
  for i in list(range(25))+list(range(78,101)):self.assertEqual(out['rows'][i],a[0]['rows'][i])
  for k in module.SIDECARS:self.assertEqual(out[k],a[0][k])
  self.assertTrue(all(out[k] is False for k in module.FLAGS))
if __name__=='__main__':unittest.main()
