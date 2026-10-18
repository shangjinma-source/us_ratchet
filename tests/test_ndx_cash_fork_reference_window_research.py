from copy import deepcopy
from decimal import Context, Decimal, Inexact, ROUND_DOWN, localcontext
from fractions import Fraction
import unittest
from backtest import ndx_cash_fork_reference_window_research as module


def fixture():
    days=['2023-05-01','2023-05-02']; full=['2023-04-28']+days
    flow=[{'session':days[0],'amount_usd':'1000','timing':module.TIMING}]
    return dict(initial_session=full[0],observed_sessions=days,
        candidate_cumulative_twr=[{'session':day,'cumulative_twr':module.ratio(value)} for day,value in zip(days,(Fraction(-1,10),Fraction(1,10)))],
        control_cumulative_twr=[{'session':day,'cumulative_twr':module.ratio(Fraction(0))} for day in days],
        incumbent_rows=[{'session':day,'value':value} for day,value in zip(full,('100','120','108'))],
        nav_rows=[{'session':day,'value':value,'nav_date':'2023-04-28' if index<2 else day}
                  for index,(day,value) in enumerate(zip(full,('2','2','2.02')))],
        candidate_flow_events=deepcopy(flow),control_flow_events=deepcopy(flow),
        candidate_currency='USD',control_currency='USD',incumbent_currency='USD',nav_currency='CNY')


class WindowTests(unittest.TestCase):
    def test_exact_four_roles_return_dd_and_nav_lag(self):
        value=module.compare_reference_window(**fixture()); roles=value['roles']
        self.assertEqual(module.from_ratio(roles['candidate']['cumulative_return']),Fraction(1,10))
        self.assertEqual(module.from_ratio(roles['candidate']['maximum_drawdown']),Fraction(1,10))
        self.assertEqual(module.from_ratio(roles['saved_incumbent_different_flow_reference']['maximum_drawdown']),Fraction(1,10))
        self.assertEqual(value['nav_observation_lags'][1]['calendar_day_lag'],3)
        self.assertIsNone(value['nav_observation_lags'][1]['publication_time'])
        self.assertFalse(value['formal_dual_benchmark_admission']); self.assertTrue(value['annualized_return_calculated'])
        self.assertEqual(roles['candidate']['interval_count'],2)

    def test_no_drop_no_futurefill_no_flow_substitution(self):
        for key in ('candidate_cumulative_twr','control_cumulative_twr','incumbent_rows','nav_rows'):
            args=fixture(); args[key].pop()
            with self.assertRaises(ValueError): module.compare_reference_window(**args)
        args=fixture(); args['nav_rows'][1]['nav_date']='2023-05-02'
        with self.assertRaisesRegex(ValueError,'Future'): module.compare_reference_window(**args)
        args=fixture(); args['control_flow_events'][0]['amount_usd']='1001'
        with self.assertRaisesRegex(ValueError,'Same-flow'): module.compare_reference_window(**args)

    def test_one_interval_and_hostile_context_long_decimal(self):
        args=fixture(); args['observed_sessions']=args['observed_sessions'][:1]
        for key in ('candidate_cumulative_twr','control_cumulative_twr'): args[key]=args[key][:1]
        for key in ('incumbent_rows','nav_rows'): args[key]=args[key][:2]
        args['nav_rows'][1]['value']='2.0000000000000000001'
        args['nav_rows'][1]['nav_date']='2023-05-01'
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            result=module.compare_reference_window(**args)
        self.assertEqual(result['roles']['candidate']['observation_count'],2)
        self.assertEqual(result['roles']['candidate']['interval_count'],1)
        self.assertEqual(module.from_ratio(result['roles']['fund_012922_cny_nav_reference']['cumulative_return']),Fraction(1,20000000000000000000))

    def test_zero_wealth_bool_float_and_reordered_dates_rejected(self):
        args=fixture(); args['candidate_cumulative_twr'][0]['cumulative_twr']=module.ratio(Fraction(-1))
        with self.assertRaises(ValueError): module.compare_reference_window(**args)

    def test_same_nav_date_requires_same_exact_value(self):
        args=fixture(); args['nav_rows'][1]['value']='2.01'
        with self.assertRaisesRegex(ValueError,'conflicting values'):
            module.compare_reference_window(**args)

    def test_annualization_126_intervals_exact_square(self):
        value=module.metrics(list(range(127)),[Fraction(1)]*126+[Fraction(6,5)])
        self.assertEqual(Decimal(value['annualized_return_diagnostic_decimal']),Decimal('.44'))
        self.assertEqual(value['annualization']['interval_count'],126)
        self.assertTrue(value['annualization']['annualization_is_historical_diagnostic'])

    def test_annualization_one_interval_and_noninteger_exponent_hostile_context(self):
        with localcontext() as context:
            context.prec=2; context.rounding=ROUND_DOWN; context.traps[Inexact]=True
            one=module.metrics([0,1],[Fraction(1),Fraction(2)])
            fifth=module.metrics(list(range(6)),[Fraction(1)]*5+[Fraction(11,10)])
        self.assertEqual(Decimal(one['annualized_return_diagnostic_decimal']),Decimal(2**252-1))
        self.assertTrue(one['annualization']['short_window_below_252_intervals'])
        with localcontext(Context(prec=110)):
            independent=Decimal('1.1')**(Decimal(252)/Decimal(5))-1
            self.assertLess(abs(Decimal(fifth['annualized_return_diagnostic_decimal'])-independent),Decimal('1e-75'))
        for invalid in (True,1.5,'NaN'):
            args=fixture(); args['incumbent_rows'][0]['value']=invalid
            with self.assertRaises(ValueError): module.compare_reference_window(**args)
        args=fixture(); args['observed_sessions'].reverse()
        with self.assertRaises(ValueError): module.compare_reference_window(**args)


if __name__=='__main__': unittest.main()
