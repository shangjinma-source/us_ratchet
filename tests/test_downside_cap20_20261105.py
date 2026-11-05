import unittest,importlib.util
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
from backtest.concentration_cap20_research_20261105 import capped
from backtest.downside_cap20_observer_20261105 import DownsideCandidateObserver
from backtest.downside_candidate_observer_integer_research import DownsideCandidateObserver as OriginalObserver
from docs.candidates.downside_cap20_selection_20261105 import decide_observed_for_account,apply_downside_selection
spec=importlib.util.spec_from_file_location('cap20_existing_fixture',Path(__file__).with_name('test_downside_account_candidate_20261105.py'));fixture_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture_module)
class Tests(unittest.TestCase):
 def test_integer_cap_preserves_residual_cash_and_zero(self):
  args={'entered_cash':'100','prices':{'A':'11','B':'21','C':'20'}}
  self.assertEqual(capped({'A':8,'B':1,'C':1},args),{'A':1,'C':1})
  self.assertEqual(sum(q*F(args['prices'][s]) for s,q in capped({'A':8},args).items()),11)
 def test_dynamic_total_tradable_equity_and_no_cap50_reuse(self):
  for cash,shares,equity,quantity in [('110',{},110,2),('200',{'A':2},220,4)]:
   capital,r,q=fixture_module.fixture(cash=cash,shares=shares);raw,side=decide_observed_for_account(stock_returns=r,qqq_reference=q,research_source_hashes=fixture_module.RESEARCH,max_holdings=10,guard=lambda:None,**capital)
   chosen=apply_downside_selection(raw=raw,sidecar=side,stock_returns=r,qqq_reference=q,research_source_hashes=fixture_module.RESEARCH)
   self.assertEqual(F(raw['investable_equity']),equity);self.assertEqual(chosen['target_quantities'],{'A':quantity});self.assertEqual(side['single_target_cap'],'1/5');self.assertEqual(side['coverage']['risk_evaluated'],side['coverage']['capped_unique']-side['coverage']['over_holdings_limit'])
   bad=deepcopy(side);bad['single_target_cap']='1/2'
   with self.assertRaises(ValueError):apply_downside_selection(raw=raw,sidecar=bad,stock_returns=r,qqq_reference=q,research_source_hashes=fixture_module.RESEARCH)
 def test_capping_can_raise_downside_and_must_recheck(self):
  capital,_,qqq=fixture_module.fixture(reference=F(0));days=list(qqq);returns={'A':dict.fromkeys(days,F('0.1')),'B':dict.fromkeys(days,F('-0.5'))};args=capital['search_arguments'];args.update(entered_cash='1000',prices={'A':'10','B':'10'},metadata={s:dict(ticker=s,issuer_id=s) for s in returns},training_scenarios=[{'A':F('1.1')**21,'B':F('0.5')**21} for _ in range(12)])
  before=OriginalObserver(max_holdings=10,search_arguments=args,stock_returns=returns,qqq_reference=qqq,max_risk_evaluations=10);after=DownsideCandidateObserver(max_holdings=10,search_arguments=args,stock_returns=returns,qqq_reference=qqq,max_risk_evaluations=10)
  for observer in (before,after):observer.observe({'A':50,'B':10},phase='base',evaluation_index=0);observer.end_observation()
  self.assertIn('2',before.finalize()['eligible_best_by_k']);self.assertNotIn('2',after.finalize()['eligible_best_by_k']);self.assertEqual(F('.2')*F('.1')+F('.1')*F('-.5'),F('-.03'))
 def test_cardinality_after_cap_and_zero_removal(self):
  capital,_,qqq=fixture_module.fixture();days=list(qqq);domain=['S'+str(i) for i in range(11)];args=capital['search_arguments'];args.update(entered_cash='1000',prices={s:'10' for s in domain},metadata={s:dict(ticker=s,issuer_id=s) for s in domain},training_scenarios=[{s:F(1) for s in domain} for _ in range(12)]);returns={s:dict.fromkeys(days,F(0)) for s in domain}
  for expensive,expected in [(False,False),(True,True)]:
   args['prices']['S10']='201' if expensive else '10';observer=DownsideCandidateObserver(max_holdings=10,search_arguments=args,stock_returns=returns,qqq_reference=qqq,max_risk_evaluations=10);observer.observe(dict.fromkeys(domain,1),phase='base',evaluation_index=0);observer.end_observation();side=observer.finalize();self.assertEqual('10' in side['eligible_best_by_k'],expected);self.assertEqual(side['coverage']['over_holdings_limit'],0 if expensive else 1)
 def test_incomplete_observation_fails(self):
  capital,r,q=fixture_module.fixture();args=capital['search_arguments'];args['entered_cash']='110';observer=DownsideCandidateObserver(max_holdings=10,search_arguments=args,stock_returns=r,qqq_reference=q,max_risk_evaluations=1)
  observer.observe({'A':1},phase='base',evaluation_index=0);observer.observe({'A':2},phase='base',evaluation_index=1);observer.end_observation()
  with self.assertRaisesRegex(ValueError,'INCOMPLETE'):observer.finalize()
if __name__=='__main__':unittest.main()
