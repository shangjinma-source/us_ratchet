import importlib.util,json
from pathlib import Path
from copy import deepcopy
import unittest
s=importlib.util.spec_from_file_location('selection',Path(__file__).resolve().parents[1]/'scripts/ndx_full_pool_security_group_selection_20261002.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def fixture():
 ref={'path':'derived.json','sha256':'a'*64};q={'ticker':'TEST','inventory_row_index':4,'raw_reference':{'sha256':'b'*64},'review_match':{'reference':{'path':'review'},'decision':{'selection_date':'2026-07-13','evidence_available_date':'2026-02-01','effective_from':'2026-02-01'}}}
 g={'context_ref':'c1','title_fact_indexes':[0],'ticker_fact_indexes':[1],'distinct_tickers':['TEST'],'distinct_titles':['Common Stock']}
 d={'raw_sha256':'b'*64,'extraction':{'same_context_security_groups':[g],'contexts':[{'context_id':'c1'}],'dei_facts':[{'name':'dei:Security12bTitle','resolved_text':'Common Stock','context_ref':'c1','continuation_complete':True,'context_match_count':1},{'name':'dei:TradingSymbol','resolved_text':'TEST','context_ref':'c1'}]}}
 r={'ticker':'TEST','inventory_row_index':4,'raw_sha256':'b'*64,'document_reference':ref,'all_security_groups':[deepcopy(g)],'selected_group_indexes':[0],'selected_title_fact_index':0,'context_ref':'c1','exact_title':'Common Stock','selected_group_pointer':'/extraction/same_context_security_groups/0','selected_title_fact_pointer':'/extraction/dei_facts/0','selection_reason':'EXPLICIT','status':'EXPLICIT_CONDITIONAL_CLASS_SELECTION_NOT_IDENTITY_CERTIFICATION','supporting_evidence':{'review_reference':{'path':'review'},'selection_date':'2026-07-13','evidence_available_date':'2026-02-01','effective_from':'2026-02-01','review_selection_postdates_window_start':True,'early_window_review_availability_verified':False,'local_first_available_at':None},'class_handling':None,**dict.fromkeys(m.FALSE,False)}
 return r,q,d,ref
class Tests(unittest.TestCase):
 def test_exact(self):
  x=fixture();before=deepcopy(x);self.assertEqual(m.validate_selection(*x),x[0]);self.assertEqual(x,before)
 def test_fact_pointer_class_and_permission(self):
  for mutate in [lambda r:r.update(selected_title_fact_index=True),lambda r:r.update(context_ref='wrong'),lambda r:r.update(exact_title='Notes'),lambda r:r.update(selected_group_pointer='/wrong'),lambda r:r.update(promotion_allowed=True),lambda r:r['supporting_evidence'].update(early_window_review_availability_verified=True)]:
   x=fixture();mutate(x[0])
   with self.assertRaises(ValueError):m.validate_selection(*x)
 def test_alternatives_preserved(self):
  x=fixture();x[2]['extraction']['same_context_security_groups'].append({'notes':'other'})
  with self.assertRaises(ValueError):m.validate_selection(*x)
 def test_unresolved_null(self):
  x=fixture();x[0].update(status='UNRESOLVED_EXPLICIT_SELECTION_REQUIRED',selected_group_indexes=[],selected_title_fact_index=None,context_ref=None,exact_title=None,selected_group_pointer=None,selected_title_fact_pointer=None);m.validate_selection(*x)
 def test_contract_source_and_specials(self):
  c=m.read_contract();self.assertEqual(len(c['rows']),53);by={x['ticker']:x for x in c['rows']};self.assertEqual(by['MSTR']['selected_group_indexes'],[4]);self.assertEqual(by['MSFT']['exact_title'],'Common stock, $ 0.00000625 par value per share');self.assertEqual(by['PDD']['class_handling']['ordinary_shares_per_ads'],4);self.assertFalse(by['ASML']['class_handling']['new_window_class_identity_verified'])
if __name__=='__main__':unittest.main()
