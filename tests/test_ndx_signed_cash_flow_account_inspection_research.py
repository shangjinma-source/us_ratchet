import copy,unittest
from decimal import localcontext,Inexact
from unittest.mock import patch
from backtest import ndx_signed_cash_flow_account_inspection_research as m

def fraction(n,d=1):return dict(numerator=str(n),denominator=str(d))
def hand_case():
 a=dict(initial=dict(session='2026-03-30',cash_usd='100',holdings={'A':10},close_prices={'A':'10'}),sessions=[dict(session='2026-03-31',open_prices={'A':'10'},close_prices={'A':'50'},cash_injection_usd='0',trade_shares={'A':-10}),dict(session='2026-04-01',open_prices={'A':'100'},close_prices={'A':'200'},cash_injection_usd='100',trade_shares={})],transaction_cost_bps='100')
 row=dict(previous_close_session='2026-03-30',session='2026-03-31',previous_close_equity_usd='200',pre_flow_open_equity_usd='200',cash_injection_usd='0',post_flow_pre_fee_open_equity_usd='200',post_trade_open_equity_usd='199',close_equity_usd='199',gross_buy_usd='0',gross_sell_usd='100',fees_usd='1',cash_after_usd='199',holdings_before={'A':10},trade_shares={'A':-10},holdings_after={'A':0},overnight_pnl_usd='0',intraday_mark_pnl_before_fees_usd='0',after_flow_pnl_net_fees_usd='-1',cash_flow_adjusted_pnl_usd='-1',overnight_return=fraction(0),after_flow_return=fraction(-1,200),session_twr=fraction(-1,200),cumulative_twr=fraction(-1,200))
 second=dict(previous_close_session='2026-03-31',session='2026-04-01',previous_close_equity_usd='199',pre_flow_open_equity_usd='199',cash_injection_usd='100',post_flow_pre_fee_open_equity_usd='299',post_trade_open_equity_usd='299',close_equity_usd='299',gross_buy_usd='0',gross_sell_usd='0',fees_usd='0',cash_after_usd='299',holdings_before={'A':0},trade_shares={},holdings_after={'A':0},overnight_pnl_usd='0',intraday_mark_pnl_before_fees_usd='0',after_flow_pnl_net_fees_usd='0',cash_flow_adjusted_pnl_usd='0',overnight_return=fraction(0),after_flow_return=fraction(0),session_twr=fraction(0),cumulative_twr=fraction(-1,200))
 flags=('zero_capital_inception_supported','broker_settlement_or_intraday_ordering_verified','single_replacement_action_semantics_verified','cash_buffer_and_risk_gates_evaluated','dividends_modelled','corporate_actions_modelled','cash_interest_modelled','withdrawals_supported','exchange_session_adjacency_verified','historical_experiment_executed','orders_executed','point_in_time_verified','promotion_allowed')
 saved=dict(schema='SIGNED_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1',rows=[row,second],initial_equity_usd='200',terminal_equity_usd='299',total_cash_injection_usd='100',total_fees_usd='1',net_dollar_pnl_excluding_injections_usd='-1',chained_twr=fraction(-1,200),transaction_cost_bps='100',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_BASKET_AND_BOTH_SIDE_FEES',arithmetic='EXACT_RATIONAL_VALUES_FINITE_DECIMAL_MONEY_NO_FLOAT_INPUT',execution_assumption='SAME_OPEN_NET_CASH_SETTLEMENT_SELL_PROCEEDS_AVAILABLE_FOR_BUYS',parameter_authority='CALLER_SUPPLIED_SYNTHETIC_OR_EXPLICIT_SCENARIO_NOT_SOURCE_BOUND',engineering_resource_limits_not_investment_policy=dict(sessions=512,security_ids=256,ratio_bits=12000),**dict.fromkeys(flags,False))
 return a,saved
class Tests(unittest.TestCase):
 def test_hand_cash_sale_fee_zero_keys_later_flow_hostile_context(self):
  a,s=hand_case();original=copy.deepcopy((a,s))
  with localcontext()as c:
   c.prec=1;c.traps[Inexact]=True;r=m.inspect_saved_signed_account(**a,saved_result=s)
  self.assertEqual(r['status'],'PASS');self.assertEqual(r['session_count'],2);self.assertEqual((a,s),original)
  self.assertTrue(r['all_saved_rows_and_fields_checked']);self.assertFalse(r['producer_called'])
 def test_saved_rows_clock_types_and_additional_fields_rejected(self):
  for attack in ('fee','cash_reset','flow_clock','timing','bool','extra','tuple','zero_key','first_snapshot'):
   a,s=hand_case()
   if attack=='fee':s['rows'][0]['fees_usd']='0'
   elif attack=='cash_reset':s['rows'][1]['cash_after_usd']='200'
   elif attack=='flow_clock':s['rows'][1]['pre_flow_open_equity_usd']='299'
   elif attack=='timing':s['cash_event_timing']='BEFORE_OLD_HOLDINGS_MARK'
   elif attack=='bool':s['point_in_time_verified']=0
   elif attack=='extra':s['rows'][1]['hidden_return']='0'
   elif attack=='tuple':s['rows']=tuple(s['rows'])
   elif attack=='zero_key':s['rows'][1]['holdings_before']={}
   else:s['rows'][0]['holdings_after']['A']=1
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_saved_signed_account(**a,saved_result=s)
 def test_real_synthetic_schema_compatibility_no_producer_during_inspection(self):
  from backtest import ndx_signed_cash_flow_return_accounting_research as producer
  from test_ndx_signed_cash_flow_accounting_review_20261003 import fixture
  a=fixture();s=producer.account_path(**a)
  with patch.object(producer,'account_path',side_effect=AssertionError('No producer execution')):self.assertEqual(m.inspect_saved_signed_account(**a,saved_result=s)['status'],'PASS')
 def test_bad_inputs_even_when_saved_summary_unchanged(self):
  for attack in ('signed_bool','missing_zero_price','negative_flow','date','zero_capital'):
   a,s=hand_case()
   if attack=='signed_bool':a['sessions'][0]['trade_shares']['A']=False
   elif attack=='missing_zero_price':a['sessions'][1]['open_prices']={}
   elif attack=='negative_flow':a['sessions'][1]['cash_injection_usd']='-1'
   elif attack=='date':a['sessions'][1]['session']='2026-03-31'
   else:a['initial'].update(cash_usd='0',holdings={},close_prices={})
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_saved_signed_account(**a,saved_result=s)
if __name__=='__main__':unittest.main()
