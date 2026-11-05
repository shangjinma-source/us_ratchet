import unittest
from fractions import Fraction as F
from scripts.research.hsbc_trade25_fee_sensitivity_20261106 import standard_fee,quote_scenario,analyze
class FeeTests(unittest.TestCase):
 def quote(self,prior):return quote_scenario(prior_hkd=prior,quantity=1,gross_usd=10000,executed_at='2024-01-02T14:30:00Z',month='2024-01')
 def test_verified_first_crossing_waived(self):
  q,low,high=self.quote(249999);self.assertEqual(q['status'],'WAIVED_INCLUDING_FIRST_CROSSING');self.assertEqual((low,high),(0,0))
 def test_only_exact_prethreshold_unresolved(self):
  q,low,high=self.quote(250000);self.assertEqual((low,high),(0,18));self.assertEqual(self.quote(250001)[1:],(18,18))
 def test_quantity(self):self.assertEqual(standard_fee(1000),18);self.assertEqual(standard_fee(1001),F('18.015'))
 def test_hk_month_boundary_intraday_unknown(self):
  b=dict(status='BLOCKED',order_log=[dict(date='2024-01-31',side='SELL',quantity=1,price=10,phase='INTRADAY_STOP_FIRST')]);r=analyze(b)
  self.assertIn('2024-01',r['scenarios'][0]['monthly']);self.assertIn('2024-02',r['scenarios'][1]['monthly'])
if __name__=='__main__':unittest.main()
