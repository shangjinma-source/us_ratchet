import copy,unittest
from test_ndx_saved_conditional_evidence_links_wrapper_20261002 import fixture,module
class LinksWrapperIndependentReview(unittest.TestCase):
 def test_full_preservation_and_exact_contract_references(self):
  args=fixture();old=copy.deepcopy(args[:4]);out=module.assemble(*args)
  self.assertEqual(args[:4],tuple(old));self.assertEqual(len(out['rows']),101)
  self.assertEqual(out['historical_denominators'],old[0]['inventory_preserved']['historical_denominators'])
  for i,call in enumerate(args[4].call_args_list):
   self.assertEqual(call.kwargs['selection_contract']['reviewed_contract_reference'],dict(args[3]['selection'],json_pointer='/rows/'+str(i)))
   self.assertEqual(out['links'][i]['queue_reference']['json_pointer'],'/inventory_preserved/extraction_queue/'+str(i))
  self.assertEqual(out['summary']['preserved_existing_coordinate_count'],25)
  self.assertEqual(out['summary']['new_typed_panel_column_count'],0)
 def test_last_row_changes_and_missing_document_never_complete(self):
  for mutate in (lambda a:a[1]['rows'][-1].update(ticker='wrong'),lambda a:a[2].pop(next(iter(a[2]))),lambda a:a[1]['rows'][-1]['supporting_evidence'].update(early_window_review_availability_verified=0),lambda a:a[0]['extraction_rows'][-1].update(document_sha256='e'*64)):
   a=fixture();mutate(a)
   with self.assertRaises(ValueError):module.assemble(*a)
 def test_ads_and_asml_special_evidence_cannot_upgrade(self):
  for ticker in ('ASML','PDD'):
   a=fixture();b,s,docs,refs,link=a;q=b['inventory_preserved']['extraction_queue'][0]
   q['ticker']=ticker;b['inventory_preserved']['rows'][25]['ticker']=ticker;b['extraction_rows'][0]['original_queue_item']=copy.deepcopy(q);s['rows'][0]['ticker']=ticker
   handling={'source_references':{'identity.json':refs['asml_evidence'],'publication.json':refs['asml_publication']},'new_window_class_identity_verified':False} if ticker=='ASML' else {'ordinary_shares_per_ads':4,'holdings_conversion_performed':False,'price_conversion_performed':False}
   s['rows'][0]['class_handling']=handling;module.assemble(*a)
   if ticker=='ASML':handling['source_references']['identity.json']={'path':'different','sha256':'a'*64}
   else:handling['price_conversion_performed']=0
   with self.assertRaises(ValueError):module.assemble(*a)
if __name__=='__main__':unittest.main()
