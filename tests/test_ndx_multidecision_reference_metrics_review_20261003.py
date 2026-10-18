"""Independent metric equations, mode separation, and input boundaries."""
from copy import deepcopy
from fractions import Fraction
from decimal import Decimal, localcontext, Inexact
import unittest
from backtest import ndx_multidecision_reference_metrics_research as core
from test_ndx_same_window_nav_reference_metrics_research import fixture, resign


class Review(unittest.TestCase):
    def test_binary64_values_actual_interval_count_and_intermediate_peak(self):
        dates = ['2026-03-31','2026-04-01','2026-04-02','2026-04-03']
        daily = [dict(session=d, normalized_twr=v, total_value_usd=1e8*i)
                 for i,(d,v) in enumerate(zip(dates,[1.,1.5,.75,1.125]))]
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            result=core.account_twr_metrics(daily=daily,calendar=dates)['metrics']
        self.assertEqual(result['interval_count'],3)
        self.assertEqual(result['maximum_drawdown'], {'numerator':'1','denominator':'2'})
        self.assertEqual(result['cumulative_return'], {'numerator':'1','denominator':'8'})
        expected=Fraction(9,8)**84-1
        with localcontext() as context:
            context.prec=100
            exact=Decimal(expected.numerator)/Decimal(expected.denominator)
            self.assertLess(abs(Decimal(result['annualized_return_diagnostic_decimal'])-exact),Decimal('1e-70'))
        daily[-1]['normalized_twr']=1.1
        result=core.account_twr_metrics(daily=daily,calendar=dates)['metrics']['cumulative_return']
        self.assertEqual(Fraction(int(result['numerator']),int(result['denominator'])),Fraction(1.1)-1)
        self.assertNotEqual(Fraction(1.1)-1,Fraction(1,10))

    def test_two_modes_diverge_and_missing_does_not_shrink_calendar(self):
        args=fixture(); args['reference_calendar']['dates']=args['alignment']['session_dates'][-4:]
        for j,row in enumerate(args['alignment']['rows'][-4:]):
            for mode,series in zip(core.saved_nav.MODES,(['1','2','1','1'],['1','1','1','2'])):
                row['conversions'][mode].update(nav_usd_exact=series[j],nav_usd_decimal=series[j])
        resign(args['alignment']);before=deepcopy(args);out=core.reference_metrics(**args)
        self.assertEqual(args,before)
        self.assertEqual(out['modes'][core.saved_nav.MODES[0]]['metrics']['maximum_drawdown'],{'numerator':'1','denominator':'2'})
        self.assertEqual(out['modes'][core.saved_nav.MODES[1]]['metrics']['cumulative_return'],{'numerator':'1','denominator':'1'})
        missing=args['alignment']['rows'][-2]['conversions'][core.saved_nav.MODES[0]]
        missing.update(status='MISSING_ALIGNMENT_INPUT',reason='SAME_SESSION_ND',nav_usd_exact=None,nav_usd_decimal=None)
        resign(args['alignment']);out=core.reference_metrics(**args)
        self.assertEqual(len(out['modes'][core.saved_nav.MODES[0]]['observations']),4)
        self.assertIsNone(out['modes'][core.saved_nav.MODES[0]]['metrics'])
        self.assertIsNotNone(out['modes'][core.saved_nav.MODES[1]]['metrics'])

    def test_no_forged_initial_or_fx_basis_and_no_calendar_compression(self):
        dates=['2026-03-31','2026-04-01']
        for first in (True,1.0000000001,0.):
            with self.subTest(first=first),self.assertRaises(ValueError):
                core.account_twr_metrics(daily=[dict(session=d,normalized_twr=v)for d,v in zip(dates,[first,1.])],calendar=dates)
        for attack in ('basis','flag','compression','direction'):
            args=fixture()
            if attack=='basis':args['alignment']['rows'][-1]['conversions'][core.saved_nav.MODES[0]]['denominator_basis']='NAV_DATE_FX'
            elif attack=='flag':args['alignment']['execution_authorized']=0
            elif attack=='direction':args['alignment']['fx_context_preserved']['rate_direction']='USD_PER_CNY'
            else:args['reference_calendar']['dates'].pop(1)
            resign(args['alignment'])
            with self.subTest(attack=attack),self.assertRaises(ValueError):core.reference_metrics(**args)


if __name__=='__main__':unittest.main()
