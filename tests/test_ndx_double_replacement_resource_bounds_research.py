import gzip,random,unittest
from fractions import Fraction as F
from backtest import ndx_double_replacement_resource_bounds_research as b

class Tests(unittest.TestCase):
 def test_rational_bound_including_zero_and_negative(self):
  for n in range(30):
   for d in range(1,30):
    for sign in (-1,1):self.assertLessEqual(len(str(F(sign*n,d))),b.rational_length(n,d))
 def test_synthetic_rectangle_bounds_without_evaluator(self):
  row=dict(execution_prices={'a':'2.5','b':'3','c':'1.25','d':'2'},holdings={'a':2,'b':3},securities={s:{'risk_chain':s} for s in 'abcd'},target_weights={'a':'0.3','b':'0.7'},transaction_cost_bps='10',starting_cash_usd='5',cash_event={'amount_usd':'2'})
  pair=dict(financial_bound={'joint_budget_usd':'20','incoming_unit_costs_with_buy_fee_usd':['1.25125','2.002']},outgoing_security_ids=['a','b'],incoming_security_ids=['c','d'],sell_quantities={'a':2,'b':3},pair_index=0,enumerable_integer_count=10)
  case=dict(identity={'original_input_row':row},identity_sha256='a'*64,scenario_index=0)
  bound=b.pair_bound(case,pair,rule='test',flags={},checks=('one',),full_count=10)
  for x in range(1,15):
   for y in range(1,10):
    if F('1.25125')*x+F('2.002')*y>20:continue
    stock=F('1.25')*x+2*y;weights=[F('1.25')*x/stock,2*y/stock]
    for w in weights:self.assertLessEqual(len(str(w)),bound['weight_chars'])
    neff=stock*stock/((F('1.25')*x)**2+(2*y)**2)
    self.assertLessEqual(len(str(neff)),bound['effective_chars'])
    self.assertLessEqual(len(str(sum(weights)+1)),bound['l1_chars'])
 def test_gzip_bound_synthetic_bytes_only(self):
  rng=random.Random(0)
  for size in (0,1,4095,4096,16384,100000):
   raw=rng.randbytes(size);self.assertLessEqual(len(gzip.compress(raw,compresslevel=6,mtime=0)),b.gzip_default_zlib_bound(size))
 def test_aggregate_all_points_and_ceiling_batch(self):
  r=b.aggregate([{'row_bytes':30,'count':11},{'row_bytes':40,'count':12}],100,10)
  self.assertEqual((r['point_count'],r['batch_count']),(23,3))
  self.assertEqual(r['full_normal_raw_bytes_upper'],11*31+12*41+300)
  self.assertFalse(r['dispatch_authorized'])
if __name__=='__main__':unittest.main()
