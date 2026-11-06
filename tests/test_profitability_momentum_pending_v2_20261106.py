import unittest
from scripts.research.screen_profitability_momentum_control_v2_20261106 import affordable_targets
class PendingBudget(unittest.TestCase):
 def verify(self,equity,names,prior,pending):
  t,c,f=affordable_targets(equity,names,prior,pending)
  self.assertGreaterEqual(c,-1e-8);self.assertAlmostEqual(sum(t.values())+c+f,equity,places=7)
  self.assertAlmostEqual(f,.0005*sum(abs(t.get(s,0)-prior.get(s,0)) for s in set(t)|set(prior)),places=7)
  return t,c,f
 def test_actual_pton_must_not_top_up(self):
  names=['PTON']+[str(i) for i in range(9)];prior={s:2051.031400 for s in names};prior['PTON']=1708.089397
  t,c,f=self.verify(20520.,names,prior,{'PTON'});self.assertEqual(t['PTON'],1708.089397);self.assertGreater(c,300)
 def test_pending_target_can_reduce_not_force_old_value(self):
  t,_,_=self.verify(20000,['P'],{'P':4000},{'P'});self.assertEqual(t['P'],2000)
 def test_full_new_portfolio_fees(self):
  t,c,f=self.verify(20000,list('abcdefghij'),{},set());self.assertAlmostEqual(sum(t.values()),20000/1.0005,places=7)
 def test_pending_not_selected_is_sold_without_replacement(self):
  t,c,f=self.verify(20000,['A'],{'P':2000},{'P'});self.assertNotIn('P',t);self.assertEqual(t['A'],2000);self.assertAlmostEqual(f,2.)
if __name__=='__main__':unittest.main()
