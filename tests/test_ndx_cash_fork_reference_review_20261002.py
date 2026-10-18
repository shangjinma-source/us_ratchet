import unittest
from copy import deepcopy
from fractions import Fraction as F
from decimal import localcontext, Inexact, Context, Decimal
from unittest.mock import Mock
import test_ndx_cash_fork_reference_window_research as owner
import test_ndx_topup_reference_comparison_20261002 as wrapper_owner
from backtest import ndx_cash_fork_reference_window_research as pure
from scripts import ndx_topup_reference_comparison_20261002 as wrapper

class ReferenceReview(unittest.TestCase):
 def test_exact_peak_drawdown_initial_and_roles_do_not_upgrade(self):
  args=owner.fixture()
  args['candidate_cumulative_twr'][0]['cumulative_twr']={'numerator':'-1','denominator':'5'}
  args['candidate_cumulative_twr'][1]['cumulative_twr']={'numerator':'-1','denominator':'10'}
  with localcontext() as ctx:
   ctx.prec=1;ctx.traps[Inexact]=True
   result=pure.compare_reference_window(**args)
  self.assertEqual(pure.from_ratio(result['roles']['candidate']['maximum_drawdown']),F(1,5))
  self.assertEqual(pure.from_ratio(result['roles']['candidate']['cumulative_return']),F(-1,10))
  self.assertEqual(pure.from_ratio(result['comparisons']['saved_incumbent_different_flow_reference']['candidate_minus_reference_return']),F(-18,100))
  self.assertEqual(result['roles']['candidate']['interval_count'],2)
  self.assertTrue(result['annualized_return_calculated'])
  for role in result['roles'].values():self.assertFalse(role['formal_admission_allowed'])
  self.assertFalse(result['roles']['saved_incumbent_different_flow_reference']['flow_equivalent_to_candidate'])
  self.assertTrue(result['roles']['same_flow_zero_trade_control']['flow_equivalent_to_candidate'])
  self.assertTrue(all(x['publication_time'] is None for x in result['nav_observation_lags']))

 def test_clock_flow_currency_and_zero_wealth_reject(self):
  attacks=[lambda a:a.update(nav_currency='USD'),lambda a:a['control_flow_events'][0].update(timing='AFTER_FEES'),lambda a:a['nav_rows'][1].update(nav_date='2023-05-02'),lambda a:a['nav_rows'][2].update(nav_date='2023-04-27'),lambda a:a['candidate_cumulative_twr'][1].update(session='2023-05-03'),lambda a:a['candidate_cumulative_twr'][1].update(cumulative_twr={'numerator':'-2','denominator':'1'})]
  for attack in attacks:
   args=owner.fixture();attack(args)
   with self.assertRaises(ValueError):pure.compare_reference_window(**args)

 def test_wrapper_full_synthetic_real_pure_twr_ignores_fake_equity(self):
  docs,refs=wrapper_owner.fixture();before=deepcopy(docs)
  compare=Mock(side_effect=pure.compare_reference_window)
  result=wrapper.assemble(docs,refs,compare)
  self.assertEqual(compare.call_count,40);self.assertEqual(docs,before)
  self.assertEqual([x['comparison']['roles']['candidate']['interval_count'] for x in result['rows'][:10]],[87,87,65,65,44,44,24,24,1,1])
  self.assertEqual(pure.from_ratio(result['rows'][0]['comparison']['roles']['candidate']['cumulative_return']),F(86,100))
  self.assertEqual(pure.from_ratio(result['rows'][-1]['comparison']['roles']['candidate']['cumulative_return']),0)
  self.assertEqual(result['rows'][0]['input_row']['gaps'],['kept'])
  self.assertIn('WITHOUT_THIS_INJECTION',result['rows'][0]['source_role_limitations']['saved_incumbent'])
  for flag,expected in wrapper.FLAGS.items():self.assertIs(result[flag],expected)

 def test_nav_same_observation_cannot_change_value(self):
  args=owner.fixture();args['nav_rows'][1]['value']='2.1'
  with self.assertRaises(ValueError):pure.compare_reference_window(**args)


 def test_annualization_exact_intervals_and_isolated_context(self):
  for n,terminal in ((1,F(101,100)),(2,F(9,10)),(5,F(11,10)),(252,F(11,10))):
   wealth=[F(1)]*n+[terminal]
   with localcontext(Context(prec=110)) as ctx:
    exact_terminal=Decimal(terminal.numerator)/Decimal(terminal.denominator)
    independent=(exact_terminal.ln()*Decimal(252)/Decimal(n)).exp()-1
   with localcontext() as hostile:
    hostile.prec=2;hostile.traps[Inexact]=True
    got=pure.metrics(list(range(n+1)),wealth)
   with localcontext(Context(prec=110)):
    self.assertLess(abs(Decimal(got['annualized_return_diagnostic_decimal'])-independent),Decimal('1e-76'))
   self.assertEqual(pure.from_ratio(got['cumulative_return']),terminal-1)
   self.assertEqual(pure.from_ratio(got['maximum_drawdown']),max(F(0),1-terminal))
   self.assertEqual(got['annualization']['interval_count'],n)
   self.assertEqual(got['annualization']['decimal_precision'],80)
   self.assertIs(got['annualization']['short_window_below_252_intervals'],n<252)
   self.assertFalse(got['annualization']['formal_admission_allowed'])

if __name__=='__main__':unittest.main()
