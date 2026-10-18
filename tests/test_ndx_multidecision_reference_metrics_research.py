from copy import deepcopy
from fractions import Fraction
from unittest import TestCase, main
from backtest import ndx_multidecision_reference_metrics_research as module
from test_ndx_same_window_nav_reference_metrics_research import fixture, resign


class ReferenceMetricsTests(TestCase):
    def test_arbitrary_contiguous_window_uses_actual_interval_count(self):
        arguments = fixture()
        arguments['reference_calendar']['dates'] = arguments['alignment']['session_dates'][-120:]
        before = deepcopy(arguments)
        result = module.reference_metrics(**arguments)
        for mode in module.saved_nav.MODES:
            metric = result['modes'][mode]['metrics']
            self.assertEqual(metric['interval_count'], 119)
            self.assertEqual(metric['observation_count'], 120)
            self.assertEqual(metric['annualization']['interval_count'], 119)
        self.assertEqual(arguments, before)
        arguments['reference_calendar']['dates'].pop(1)
        with self.assertRaisesRegex(ValueError, 'compression'):
            module.reference_metrics(**arguments)

    def test_missing_strict_blocks_whole_mode_without_borrowing_backward(self):
        arguments = fixture()
        arguments['reference_calendar']['dates'] = arguments['alignment']['session_dates'][-120:]
        conversion = arguments['alignment']['rows'][-5]['conversions'][module.saved_nav.MODES[0]]
        conversion.update(status='MISSING_ALIGNMENT_INPUT', reason='NO_SAME_SESSION_FX',
                          nav_usd_exact=None, nav_usd_decimal=None)
        resign(arguments['alignment'])
        result = module.reference_metrics(**arguments)
        self.assertIsNone(result['modes'][module.saved_nav.MODES[0]]['metrics'])
        self.assertIsNotNone(result['modes'][module.saved_nav.MODES[1]]['metrics'])

    def test_saved_twr_ignores_injected_equity_and_keeps_initial_peak(self):
        calendar = ['2026-03-31', '2026-04-01', '2026-04-02']
        daily = [dict(session=d, normalized_twr=value, total_value_usd=equity)
                 for d, value, equity in zip(calendar, [1., .5, 1.], [100, 1050, 2100])]
        output = module.account_twr_metrics(daily=daily, calendar=calendar)['metrics']
        self.assertEqual(output['interval_count'], 2)
        self.assertEqual(output['cumulative_return'], {'numerator':'0','denominator':'1'})
        self.assertEqual(output['maximum_drawdown'], {'numerator':'1','denominator':'2'})
        daily[0]['normalized_twr'] = True
        with self.assertRaises(ValueError):
            module.account_twr_metrics(daily=daily, calendar=calendar)


if __name__ == '__main__':
    main()
