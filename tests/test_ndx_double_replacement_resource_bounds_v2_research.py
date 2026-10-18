import unittest
from fractions import Fraction as F
from backtest import ndx_double_replacement_resource_bounds_v2_research as b
from backtest import ndx_double_replacement_evaluation_research as synthetic_oracle

class Tests(unittest.TestCase):
 def test_all_fields_synthetic_only_and_digit_bins(self):
  row=dict(execution_prices={'a':'2.5','b':'3','c':'1.25','d':'2','e':'4.5'},holdings={'a':2,'b':3,'e':2},securities={s:dict(risk_chain=s,issuer_id=s) for s in 'abcde'},target_weights={'a':'0.3','b':'0.7'},transaction_cost_bps='10',starting_cash_usd='5',cash_event={'amount_usd':'2'},minimum_cash_buffer_usd='1',risk_parameters=dict(max_single_weight='0.9',min_single_weight='0.01',top_weight_cap='1',minimum_effective_n_ratio='0.5',risk_chain_top1_cap='1'))
  sale=F(14);budget=F(5+2)+sale*(1-F('0.001'))-1
  costs=[F('1.25125'),F('2.002')];points=[(x,y) for x in range(1,20) for y in range(1,20) if costs[0]*x+costs[1]*y<=budget]
  pair=dict(financial_bound={'joint_budget_usd':str(budget),'incoming_unit_costs_with_buy_fee_usd':list(map(str,costs))},outgoing_security_ids=['a','b'],incoming_security_ids=['c','d'],sell_quantities={'a':2,'b':3},pair_index=0,enumerable_integer_count=len(points),first_global_ordinal=5)
  case=dict(identity={'original_input_row':row},identity_sha256='a'*64,scenario_index=0)
  bound=b.pair_bound(case,pair,rule='test',flags={},checks=synthetic_oracle.CHECKS,full_count=5+len(points))
  saved=0;maxq=[max(p[i] for p in points) for i in (0,1)];last=5+len(points)-1
  for index,(x,y) in enumerate(points):
   task=dict(proposed_holdings={'a':0,'b':0,'c':x,'d':y,'e':2},signed_trade_quantities={'a':-2,'b':-3,'c':x,'d':y,'e':0})
   actual=synthetic_oracle.evaluate_one(row,task)
   for field,limit in bound['field_char_bounds'].items():self.assertLessEqual(len(actual[field]),limit,field)
   for sid,value in actual['risk']['weights'].items():self.assertLessEqual(len(value),bound['weight_char_bounds'][sid])
   for chain,value in actual['risk']['risk_chain_weights'].items():self.assertLessEqual(len(value),bound['chain_char_bounds'][chain])
   self.assertLessEqual(len(actual['risk']['effective_n']),bound['effective_chars'])
   saved+=3*sum(len(str(qmax))-len(str(q)) for q,qmax in zip((x,y),maxq))+2*(len(str(last))-len(str(index+5)))
  self.assertEqual(saved,bound['integer_digit_savings'])
 def test_positive_rational_lengths_and_aggregation(self):
  for n in range(30):
   for d in range(1,30):self.assertLessEqual(len(str(F(n,d))),b.positive_length(n,d))
  r=b.aggregate([dict(row_bytes=100,count=10,integer_digit_savings=23)],50,10)
  self.assertEqual(r['full_normal_raw_bytes_upper'],1037)
if __name__=='__main__':unittest.main()
