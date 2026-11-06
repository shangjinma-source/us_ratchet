import unittest
from scripts.research.screen_profitability_daily_regime_20261106 import market_states,affordable_targets
from datetime import date,timedelta
class RegimeTests(unittest.TestCase):
 def series(self,tail):
  values=[100.]*200+tail
  return {(date(2020,1,1)+timedelta(days=i)).isoformat():v for i,v in enumerate(values)}
 def test_two_completed_closes(self):
  p=self.series([110.,111.,90.,89.]);s=market_states(p);d=sorted(p)
  self.assertFalse(s[d[200]]);self.assertTrue(s[d[201]]);self.assertTrue(s[d[202]]);self.assertFalse(s[d[203]])
 def test_future_does_not_change_prior(self):
  a=self.series([110.,111.,90.,89.]);b=dict(a);b[sorted(b)[-1]]=10000.
  x=market_states(a);y=market_states(b)
  for d in sorted(a)[:-1]:self.assertEqual(x.get(d),y.get(d))
 def test_requires_previous_indicator(self):
  p=self.series([]);self.assertEqual(market_states(p),{})
 def test_pending_reentry_never_tops_up(self):
  targets,cash,fee=affordable_targets(20000.,['x','y'],{'x':900.}, {'x'})
  self.assertLessEqual(targets['x'],900.);self.assertGreaterEqual(cash,0)
  self.assertAlmostEqual(sum(targets.values())+cash+fee,20000.)
if __name__=='__main__':unittest.main()
