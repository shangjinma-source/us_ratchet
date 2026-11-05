import unittest,importlib.util
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from scripts.research.review_downside_cap20_account_20261105 import score,review_selection
from docs.candidates.downside_cap20_selection_20261105 import decide_observed_for_account,apply_downside_selection
spec=importlib.util.spec_from_file_location('audit_fixture',Path(__file__).with_name('test_downside_account_candidate_20261105.py'));fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
class Tests(unittest.TestCase):
 def test_independent_cap_refuses_21_percent(self):
  args=dict(entered_cash='100',fee_bps='0',prices={'A':'1'},metadata={'A':{'issuer_id':'A'}},minimum_cash_buffer='0',training_scenarios=[{'A':'1'}]*12)
  self.assertEqual(score({'A':20},args)['residual_cash'],80)
  with self.assertRaisesRegex(ValueError,'CAP20'):score({'A':21},args)
 def test_independent_selection_rejects_owner_and_target_tamper(self):
  capital,r,q=fixtures.fixture(cash='110');raw,side=decide_observed_for_account(stock_returns=r,qqq_reference=q,research_source_hashes=fixtures.RESEARCH,max_holdings=10,guard=lambda:None,**capital);selected=apply_downside_selection(raw=raw,sidecar=side,stock_returns=r,qqq_reference=q,research_source_hashes=fixtures.RESEARCH)
  proof,report=review_selection(selected,side,r,q,fixtures.RESEARCH);self.assertEqual(report['target'],{'A':2})
  with self.assertRaisesRegex(ValueError,'DYNAMIC_BINDING'):review_selection(selected,side,r,q,{'wrong':'pin'})
  bad=deepcopy(selected);bad['target_quantities']={'A':3}
  with self.assertRaises(ValueError):review_selection(bad,side,r,q,fixtures.RESEARCH)
if __name__=='__main__':unittest.main()
