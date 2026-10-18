"""Independent bounded synthetic rounding/domain tests."""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import unittest
from backtest.ndx_target_cash_neighbors_research import generate_target_neighbors as generate
import test_ndx_target_cash_neighbors_research as f
class Review(unittest.TestCase):
 def test_all_small_budgets_are_exact_zero_first_domain_prefix(self):
  for cash in ('0','1','11','100'):
   for cap in (0,1,8):
    value=f.fixture();value.update(starting_cash_usd=cash,buy_limits={'A':cap,'B':cap},transaction_cost_bps='100')
    full=generate(**value);choices=[full['rounding_details'][s]['clipped_choices'] for s in ('A','B')]
    domain=[{'A':0,'B':0}]
    domain += [dict(zip(('A','B'),q)) for q in product(*choices) if any(q)]
    self.assertEqual(full['plans'],domain)
    for budget in (1,2,3,4,5):
     value['max_generated_plans']=budget;r=generate(**value)
     self.assertEqual(r['plans'],domain[:budget]);self.assertEqual(r['ungenerated_count'],len(domain)-len(domain[:budget]))
 def test_old_absent_target_stock_kept_exact_deficit_budget_and_cap(self):
  value=f.fixture();value.update(holdings={'OLD':10},execution_prices={'OLD':'20','A':'10','B':'10'},target_weights={'A':'3','B':'1'},buy_limits={'A':2,'B':20},transaction_cost_bps='0')
  before=deepcopy(value);r=generate(**value)
  self.assertEqual(value,before)
  self.assertEqual(r['initial_stock_value_usd'],{'numerator':'200','denominator':'1'})
  self.assertEqual(r['deficit_scaling_factor'],{'numerator':'1','denominator':'3'})
  self.assertEqual(r['plans'],[{'A':0,'B':0},{'A':2,'B':2},{'A':2,'B':3}])
  self.assertEqual(r['normalized_target_weights']['OLD'],{'numerator':'0','denominator':'1'})
  self.assertFalse(r['old_holdings_sold']);self.assertFalse(r['portfolio_feasibility_asserted'])
 def test_empty_buy_set_and_missing_old_price(self):
  value=f.fixture();value.update(holdings={'OLD':1},execution_prices={'OLD':'10'},target_weights={'OLD':'1'},buy_limits={})
  r=generate(**value);self.assertEqual(r['plans'],[{}]);self.assertEqual(r['distinct_supplied_domain_count'],1)
  value['execution_prices']={}
  with self.assertRaises(ValueError):generate(**value)
if __name__=='__main__':unittest.main()
