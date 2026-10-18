import copy,unittest
from fractions import Fraction as F
from decimal import localcontext,Inexact
from backtest import ndx_single_replacement_result_inspection_research as m
from test_ndx_single_replacement_result_inspection_research import point,journal_fixture,resign

class Tests(unittest.TestCase):
 def test_entire_hand_oracle_two_sided_fee_stock_denominator_and_literal_l1(self):
  a=point()
  a['saved_result']=dict(status='INFEASIBLE',feasible=False,gross_sell_usd='20',gross_buy_usd='5',sell_fee_usd='1/50',buy_fee_usd='1/200',total_fee_usd='1/40',cash_after_usd='4999/40',invested_stock_usd='25',equity_after_usd='5999/40',cash_flow_adjusted_pnl_usd='-1/40',financial_checks=dict(NONNEGATIVE_CASH=True,CASH_BUFFER=True),risk=dict(checks=dict(MAX_SINGLE_WEIGHT=False,MIN_SINGLE_WEIGHT=True,SECURITY_TOP3_WEIGHT=False,MINIMUM_EFFECTIVE_N=False,RISK_CHAIN_TOP1_WEIGHT=False),all_passed=False,weights={'B':'4/5','C':'1/5'},effective_n='25/17',positive_holding_count=2,risk_chain_weights={'chain:B':'4/5','chain:C':'1/5'}),issuer_conflicts={},original_target_stock_l1='8/5')
  with localcontext()as c:
   c.prec=1;c.traps[Inexact]=True;report=m.inspect_saved_evaluation(**a)
  self.assertEqual(report['status'],'PASS');self.assertFalse(report['evaluator_called'])
  for field,bad in [('total_fee_usd','1/200'),('original_target_stock_l1','0'),('invested_stock_usd','149.975')]:
   b=copy.deepcopy(a);b['saved_result'][field]=bad
   with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_saved_evaluation(**b)

 def test_qcap_not_self_signed_and_exact_financial_slack_zero(self):
  a=point();row=a['prepared']['document']['cases'][0]['identity']['original_input_row'];task=a['task'];intervals=m.catalogue(a['prepared'])
  self.assertEqual(intervals[0][:2],(0,5)) # floor((100+10+20*.999-100)/(5*1.001))
  changed=copy.deepcopy(a['prepared']);changed['document']['cases'][0]['pairs'][0]['financial_cap_floor']=6;changed['content_sha256']=m.digest(changed['document'])
  with self.assertRaisesRegex(ValueError,'qcap'):m.catalogue(changed)
  for quantity,expected in [(5,True),(6,False)]:
   t=copy.deepcopy(task);t['signed_trade_quantities']['C']=quantity;t['proposed_holdings']['C']=quantity
   out=m.arithmetic(row,t);cash=F(100)+10+20-F(5*quantity)-F(20+5*quantity,1000)
   self.assertEqual(F(out['cash_after_usd']),cash);self.assertIs(out['financial_checks']['CASH_BUFFER'],expected)

 def test_technical_error_fields_retain_real_string_types_not_numeric_claims(self):
  for mode,stage,field in [('exception','RAW_EXCEPTION','error'),('none','POSTCHECK','validation_error')]:
   a=journal_fixture(mode)
   def mutate(records):
    p=next(x['body']['payload']for x in records if x['body']['stage']==stage);p[field]['type']=False;p[field]['message']=[]
   a['journal_bytes']=resign(a['journal_bytes'],mutate)
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_saved_journal(**a)

if __name__=='__main__':unittest.main()
