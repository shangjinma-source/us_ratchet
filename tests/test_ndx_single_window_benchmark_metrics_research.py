import copy
import unittest
from datetime import date, timedelta
from decimal import Decimal
from backtest import ndx_single_window_benchmark_metrics_research as m


def fixture():
    start = date(2026, 3, 18)
    days = [(start + timedelta(days=i)).isoformat() for i in range(126)] + ['2026-09-17']
    daily = [dict(session=day, total_value_usd=25000) for day in days]
    raw = 'Date,Close\n2026-03-17,1\n2026-03-19,2\n2026-09-18,999\n'
    return dict(calendar=days, candidate_daily=copy.deepcopy(daily), incumbent_daily=daily, nav_csv=raw)


class MetricsTests(unittest.TestCase):
    def test_hand_calculated_return_drawdown_and_interval(self):
        values = [25000, 50000, 25000] + [25000] * 123 + [30000]
        result = m.metrics(values)
        self.assertEqual(Decimal(result['path_return']), Decimal('.2'))
        self.assertEqual(Decimal(result['annualized_return_252_over_126']), Decimal('.44'))
        self.assertEqual(Decimal(result['path_max_drawdown']), Decimal('.5'))
        self.assertEqual(result['return_interval_count'], 126)
        for changed in (values[:-1], values + [30000], [True] + values[1:], [0] + values[1:]):
            with self.assertRaises(ValueError):
                m.metrics(changed)

    def test_backward_nav_and_no_authentication_upgrade(self):
        result = m.compare(**fixture())
        self.assertEqual(result['nav']['rows'][0]['nav_source_date'], '2026-03-17')
        self.assertEqual(result['nav']['rows'][-1]['nav'], '2')
        self.assertEqual(result['nav']['same_date_missing_count'], 126)
        self.assertEqual(Decimal(result['references']['nav_012922_native_currency']['path_return']), 1)
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['ledger_accounting_verified'])
        self.assertFalse(result['source_bytes_authenticated'])

    def test_reject_calendar_baseline_and_nav_ambiguity(self):
        cases = []
        value = fixture(); value['candidate_daily'][0]['total_value_usd'] = 25001; cases.append(value)
        value = fixture(); value['incumbent_daily'].pop(); cases.append(value)
        for raw in ('Date,Close\n2026-03-19,1\n', 'Date,Close\n2026-03-17,1\n2026-03-17,2\n',
                    'Date,Close\n2026-03-19,1\n2026-03-17,2\n', 'Date,Close\n2026-03-17,NaN\n'):
            value = fixture(); value['nav_csv'] = raw; cases.append(value)
        for value in cases:
            with self.assertRaises(ValueError):
                m.compare(**value)


if __name__ == '__main__':
    unittest.main()
