import unittest
from copy import deepcopy
from unittest.mock import patch
from backtest.return_priority_monthly_top1_selector import select_top1_quantities, decide_top1_for_account
class Top1Tests(unittest.TestCase):
 def args(self):return dict(prices={'A':'10','B':'30'},metadata={'A':{'ticker':'AAA','issuer_id':'I'},'B':{'ticker':'BBB','issuer_id':'J'}},training_scenarios=[{'A':'1.1','B':'1.2'} for _ in range(12)],scenario_dates=[f'2025-{m:02d}-01' for m in range(1,13)],decision_date='2025-12-31',entered_cash='100',fee_bps=0,minimum_cash_buffer=0)
 def test_exact_old_ranking_and_projection(self):
  from scripts.return_priority_top1_baselines import select_top1
  a=self.args();a['entered_cash']='20000';new=select_top1_quantities(**a);old=select_top1(a)
  self.assertEqual(new['ranked_security_id'],old['security_id']);self.assertEqual(new['selected']['quantities']['B'],old['decision_quantity']);self.assertEqual(new['selected']['actual_weights']['B'],old['modes']['TOP1_SAME_PROJECTION'])
 def test_tie_and_unaffordable_no_runnerup(self):
  a=self.args();a['entered_cash']='20';r=select_top1_quantities(**a);self.assertEqual(r['ranked_security_id'],'B');self.assertEqual(r['selected']['quantities'],{});self.assertEqual(r['selected']['residual_cash'],'20')
  a['training_scenarios']=[{'A':'1.2','B':'1.2'} for _ in range(12)];self.assertEqual(select_top1_quantities(**a)['ranked_security_id'],'A')
 def test_future_and_missing_domain_rejected(self):
  a=self.args();a['decision_date']='2025-11-30'
  with self.assertRaises(ValueError):select_top1_quantities(**a)
  a=self.args();a['training_scenarios'][0].pop('B')
  with self.assertRaises(ValueError):select_top1_quantities(**a)
 def test_account_net_equity_and_honest_calls(self):
  a=self.args();a.update(price_basis='UNIT',quote_as_of=a['decision_date']);quotes=[dict(security_id=s,price=p,as_of=a['decision_date'],price_basis='UNIT',source_references=['raw']) for s,p in a['prices'].items()]
  r=decide_top1_for_account(decision_date=a['decision_date'],account_state=dict(asof=a['decision_date'],revision='r',reserved_cash='0',cash='10',shares={'A':9}),valuation_quotes=quotes,search_arguments=a,source_hashes={'raw':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64,'backtest/return_priority_monthly_top1_selector.py':'c'*64})
  self.assertEqual(r['investable_equity'],'100');self.assertEqual(r['available_cash'],'10');self.assertEqual(r['target_quantities'],{'B':3});self.assertEqual(r['core_calls'],0);self.assertEqual(r['selector_calls'],1);self.assertEqual(r['search_result']['status'],'SELECTOR_COMPLETE')
 def test_incomplete_selector_cannot_publish_targets(self):
  a=self.args();a.update(price_basis='UNIT',quote_as_of=a['decision_date'])
  quotes=[dict(security_id=s,price=p,as_of=a['decision_date'],price_basis='UNIT',source_references=['raw']) for s,p in a['prices'].items()]
  for status in ('BLOCKED','UNKNOWN',None):
   invalid=select_top1_quantities(**a);invalid['status']=status
   with self.subTest(status=status),patch('backtest.return_priority_monthly_top1_selector.select_top1_quantities',return_value=invalid):
    with self.assertRaisesRegex(ValueError,'TOP1_SELECTOR_INCOMPLETE'):
     decide_top1_for_account(decision_date=a['decision_date'],account_state=dict(asof=a['decision_date'],revision='r',reserved_cash='0',cash='100',shares={}),valuation_quotes=quotes,search_arguments=a,source_hashes={'raw':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64,'backtest/return_priority_monthly_top1_selector.py':'c'*64})
if __name__=='__main__':unittest.main()
