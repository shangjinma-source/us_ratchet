import itertools
import unittest
from fractions import Fraction as F
from decimal import localcontext,Inexact
from backtest import ndx_min_weight_topup_closure_research as subject

class ClosureIndependentReview(unittest.TestCase):
 def test_small_grid_oracle_least_vector_and_failure_soundness(self):
  for prices,old,minimum,cash,fee in itertools.product(((1,2),(3,1)),((1,3),(0,3),(2,1)),('.2','.4','.6'),('3','8'),('0','1000')):
   caps=(3,3);seed=(1 if old[0]==0 else 0,0); threshold=F(minimum)-F(1,10**9)
   args=dict(holdings=dict(zip('AB',old)),execution_prices=dict(zip('AB',map(str,prices))),support_security_ids=['A','B'],seed_buy_shares=dict(zip('AB',seed)),buy_limits=dict(zip('AB',caps)),min_single_weight=minimum,starting_cash_usd=cash,cash_injection_usd='0',transaction_cost_bps=fee,minimum_cash_buffer_usd='1',max_iterations=50)
   feasible=[]
   for x in itertools.product(*(range(s,c+1) for s,c in zip(seed,caps))):
    gross=sum(p*q for p,q in zip(prices,x)); value=[p*(h+q) for p,h,q in zip(prices,old,x)];total=sum(value)
    if gross*(1+F(fee)/10000)<=F(cash)-1 and all(v>=threshold*total for v in value):feasible.append(x)
   got=subject.close_min_weight_topups(**args)
   for step in got['trace']:
    before=tuple(step['before_buy_shares'][s] for s in 'AB'); equity=sum(p*(h+x) for p,h,x in zip(prices,old,before))
    for i,s in enumerate('AB'):
     raw=(threshold*equity-old[i]*prices[i])/prices[i];ceil=-(-raw.numerator//raw.denominator)
     self.assertEqual(step['requirements'][s]['ceil_additional_shares'],ceil)
     self.assertEqual(step['next_buy_shares'][s],max(before[i],ceil,0))
    for y in feasible:self.assertTrue(all(step['next_buy_shares'][s]<=y[i] for i,s in enumerate('AB')))
   if got['status']=='FIXED_POINT':
    x=tuple(got['buy_shares'][s] for s in 'AB');self.assertIn(x,feasible)
    for y in feasible:self.assertTrue(all(a<=b for a,b in zip(x,y)))
   elif got['status']=='PROVEN_INFEASIBLE_UPWARD_DOMAIN':self.assertEqual(feasible,[])
   else:self.fail(got['status'])
   for flag in ('all_risks_evaluated','issuer_uniqueness_evaluated','eligibility_inferred','promotion_allowed','full_integer_space_infeasibility_claimed'):self.assertIs(got[flag],False)

 def base(self):
  return dict(holdings={'A':1,'B':9,'C':0},execution_prices={'A':'1','B':'1','C':'2'},support_security_ids=['A','B'],seed_buy_shares={'A':0,'B':0,'C':0},buy_limits={'A':20,'B':20,'C':20},min_single_weight='.4',starting_cash_usd='30',cash_injection_usd='0',transaction_cost_bps='10',minimum_cash_buffer_usd='1',max_iterations=20)

 def test_synchronous_dilution_zero_budget_and_hostile_context(self):
  args=self.base()
  with localcontext() as ctx:
   ctx.prec=1;ctx.traps[Inexact]=True
   got=subject.close_min_weight_topups(**args)
  self.assertEqual(got['status'],'FIXED_POINT')
  self.assertGreater(len(got['trace']),2)
  self.assertEqual(got['buy_shares'],{'A':5,'B':0,'C':0})
  self.assertEqual(got['effective_buy_limits']['C'],0)
  unknown=subject.close_min_weight_topups(**dict(args,max_iterations=0))
  self.assertEqual(unknown['status'],'UNKNOWN_ITERATION_BUDGET')
  self.assertIsNone(unknown['buy_shares']);self.assertIsNone(unknown['failure_certificate'])
  self.assertFalse(unknown['minimum_weight_fixed_point_verified'])

 def test_fee_strict_boundary_and_invalid_support(self):
  args=self.base();args.update(seed_buy_shares={'A':5,'B':0,'C':0},starting_cash_usd='6.005')
  self.assertEqual(subject.close_min_weight_topups(**args)['status'],'FIXED_POINT')
  args['starting_cash_usd']='6.004999999999999999'
  got=subject.close_min_weight_topups(**args)
  self.assertEqual(got['failure_certificate']['kind'],'CASH_BUFFER_EXCEEDED')
  for key,value in [('max_iterations',True),('support_security_ids',['A']),('support_security_ids',['B','A']),('seed_buy_shares',{'A':0,'B':0,'C':1}),('buy_limits',{'A':False,'B':20,'C':20}),('execution_prices',{'A':1.0,'B':'1','C':'2'})]:
   bad=self.base();bad[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):subject.close_min_weight_topups(**bad)

if __name__=='__main__':unittest.main()
