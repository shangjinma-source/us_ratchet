import unittest
from scripts.research.screen_annual_cashflow_price_diagnostic_20261106 import affordable_targets,quarterly
class CashBudget(unittest.TestCase):
 def check(self,equity,names,prior):
  target,cash,fee=affordable_targets(equity,names,prior)
  self.assertGreaterEqual(cash,-1e-8);self.assertAlmostEqual(sum(target.values())+cash+fee,equity,places=7)
  self.assertAlmostEqual(fee,sum(abs(target.get(s,0)-prior.get(s,0)) for s in set(target)|set(prior))*.0005,places=7)
  self.assertTrue(all(v<=equity/10 for v in target.values()));return target,cash,fee
 def test_ten_new_names_fee_affordable(self):
  t,c,f=self.check(20000,list('abcdefghij'),{});self.assertAlmostEqual(f,20000*.0005/1.0005,places=6)
 def test_sale_and_rotation_budget(self):
  self.check(20000,list('abcdeklmno'),{s:2000 for s in 'abcdefghij'})
 def test_less_than_ten_does_not_fill_cash(self):
  t,c,f=self.check(20000,['a','b'],{});self.assertEqual(t,{'a':2000.,'b':2000.});self.assertAlmostEqual(c,15998.)
 def test_all_cash_sale_fees(self):
  t,c,f=self.check(20000,[],{'a':10000});self.assertEqual(t,{});self.assertEqual(c,19995.)
if __name__=='__main__':unittest.main()
