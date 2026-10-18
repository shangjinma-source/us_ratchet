import copy,unittest
from decimal import localcontext,Inexact
from fractions import Fraction as F
from backtest import ndx_signed_cash_flow_return_accounting_research as m

def rate(v):return F(int(v['numerator']),int(v['denominator']))
def fixture():
 return dict(initial=dict(session='2026-03-30',cash_usd='10',holdings={'A':4},close_prices={'A':'10'}),sessions=[dict(session='2026-03-31',open_prices={'A':'15','B':'20'},close_prices={'A':'12','B':'25'},cash_injection_usd='30',trade_shares={'A':-2,'B':1}),dict(session='2026-04-01',open_prices={'A':'10','B':'20'},close_prices={'A':'11','B':'500'},cash_injection_usd='10',trade_shares={'A':1,'B':-1})],transaction_cost_bps='100')
class Tests(unittest.TestCase):
 def test_independent_partial_sale_two_injections_and_marks(self):
  a=fixture();old=copy.deepcopy(a)
  with localcontext()as ctx:
   ctx.prec=2;ctx.traps[Inexact]=True;d=m.account_path(**a)
  r,s=d['rows'];self.assertEqual(a,old)
  self.assertEqual([F(r[k])for k in ('pre_flow_open_equity_usd','post_flow_pre_fee_open_equity_usd','fees_usd','cash_after_usd','close_equity_usd')],[F(70),F(100),F(1,2),F(99,2),F(197,2)])
  self.assertEqual([F(s[k])for k in ('pre_flow_open_equity_usd','post_flow_pre_fee_open_equity_usd','fees_usd','cash_after_usd','close_equity_usd')],[F(179,2),F(199,2),F(3,10),F(346,5),F(511,5)])
  self.assertEqual(rate(r['session_twr']),F(70,50)*F(197,200)-1)
  self.assertEqual(rate(d['chained_twr']),F(70,50)*F(197,200)*F(179,197)*F(1022,995)-1)
  self.assertEqual(F(d['net_dollar_pnl_excluding_injections_usd']),F(511,5)-50-40)
  self.assertEqual(r['holdings_after'],{'A':2,'B':1});self.assertEqual(s['holdings_after'],{'A':3,'B':0})
  self.assertFalse(d['single_replacement_action_semantics_verified']);self.assertFalse(d['broker_settlement_or_intraday_ordering_verified'])
 def test_cash_only_zero_capital_and_exact_tiny_fee_boundaries(self):
  a=dict(initial=dict(session='2026-03-30',cash_usd='10',holdings={},close_prices={}),sessions=[dict(session='2026-03-31',open_prices={},close_prices={},cash_injection_usd='20',trade_shares={})],transaction_cost_bps='100')
  d=m.account_path(**a);self.assertEqual(d['terminal_equity_usd'],'30');self.assertEqual(rate(d['chained_twr']),0)
  a['initial']['cash_usd']='0'
  with self.assertRaisesRegex(ValueError,'ZERO_CAPITAL'):m.account_path(**a)
  a=fixture();a['initial']['cash_usd']='0';a['initial']['holdings']={'A':1};a['sessions']=[dict(session='2026-03-31',open_prices={'A':'10','B':'10'},close_prices={'A':'10','B':'10'},cash_injection_usd='0',trade_shares={'A':-1,'B':1})];a['transaction_cost_bps']='0.00000000000000000001'
  with self.assertRaisesRegex(ValueError,'both-side fees'):m.account_path(**a)
 def test_explicit_calendar_typed_signed_and_no_short_boundaries(self):
  for kind in ('bool','oversell','missing_zero_slot','negative_flow','duplicate_day','unknown_field'):
   a=fixture()
   if kind=='bool':a['sessions'][0]['trade_shares']['A']=False
   elif kind=='oversell':a['sessions'][0]['trade_shares']['A']=-5
   elif kind=='missing_zero_slot':del a['sessions'][1]['close_prices']['B']
   elif kind=='negative_flow':a['sessions'][0]['cash_injection_usd']='-1'
   elif kind=='duplicate_day':a['sessions'][1]['session']=a['sessions'][0]['session']
   else:a['sessions'][0]['dividend_usd']='1'
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.account_path(**a)
if __name__=='__main__':unittest.main()
