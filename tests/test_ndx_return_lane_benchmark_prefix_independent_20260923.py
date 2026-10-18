"""Bounded prefix counterexamples; never build/reexecute the benchmark account."""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest
from scripts import ndx_return_lane_benchmark_prefix_20260923 as reader


class IndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {}
        for name, (relative, expected) in reader.BOUND.items():
            raw = (reader.BASE / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Independent hard input differs')
            cls.docs[name] = json.loads(raw)
        path = next(p for p in cls.docs['nav']['source_hashes'] if p.endswith('012922.csv'))
        cls.raw = Path(path).read_bytes()
        if hashlib.sha256(cls.raw).hexdigest() != cls.docs['nav']['source_hashes'][path]:
            raise ValueError('Immutable CSV differs')
        cls.calendar, cls.prefix = reader.control_prefix(cls.docs['control'], cls.docs['oracle'], cls.docs['schedule'])

    def test_byte_bound_oracle_and_nested_nav_closure(self):
        self.assertEqual(self.docs['oracle']['daily_cash_shares_equity_rows_verified'], 295)
        self.assertFalse(self.docs['oracle']['engine_imported'])
        for path, expected in self.docs['nav']['nav']['source_hashes'].items():
            self.assertEqual(self.docs['nav']['source_hashes'][path], expected)
        self.assertEqual(len(self.prefix['daily']), 107)
        self.assertEqual(len(self.prefix['executions']), 6)

    def test_six_period_clock_and_full_calendar_cannot_be_shifted(self):
        schedule = copy.deepcopy(self.docs['schedule'])
        schedule['calendar'][schedule['calendar'].index('2023-04-03')] = '2023-04-02'
        with self.assertRaises(ValueError):
            reader.control_prefix(self.docs['control'], self.docs['oracle'], schedule)

    def test_future_csv_observation_cannot_replace_backward_value(self):
        report = copy.deepcopy(self.docs['nav'])
        row = report['nav']['rows'][0]
        row['nav_date'] = '2023-04-03'
        row['nav'] = report['nav']['rows'][1]['nav']
        with self.assertRaises(ValueError): reader.nav_prefix(report, self.raw, self.calendar)

    def test_no_fx_fee_or_publication_upgrade(self):
        for flag in ('publication_time_verified', 'fx_modelled', 'subscription_redemption_fees_modelled'):
            report = copy.deepcopy(self.docs['nav']); report['nav'][flag] = True
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                reader.nav_prefix(report, self.raw, self.calendar)
        result = reader.nav_prefix(self.docs['nav'], self.raw, self.calendar)
        self.assertEqual(result['role'], '012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV')
        self.assertFalse(result['currency_fx_equivalence_verified'])
        self.assertFalse(result['subscription_redemption_fee_equivalence_verified'])

    def test_decimal_drawdown_and_106_intervals(self):
        result = reader.metrics(['100', '200', '50'] + ['100'] * 104)
        self.assertEqual(Decimal(result['path_max_drawdown']), Decimal('.75'))
        self.assertEqual(Decimal(result['path_return']), Decimal(0))
        self.assertEqual(result['return_interval_count'], 106)


if __name__ == '__main__':
    unittest.main()
