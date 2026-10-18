from copy import deepcopy
from decimal import Decimal, Inexact, getcontext, setcontext
import json
from pathlib import Path
import unittest

from scripts import ndx_return_lane_benchmark_prefix_20260923 as module


class BenchmarkPrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {key: json.loads((module.BASE / path).read_bytes())
                         for key, (path, _) in module.BOUND.items()}
        nav = cls.documents['nav']
        cls.nav_bytes = Path(next(path for path in nav['source_hashes'] if path.endswith('012922.csv'))).read_bytes()

    def control(self, documents=None):
        documents = documents or self.documents
        return module.control_prefix(documents['control'], documents['oracle'], documents['schedule'])

    def test_real_saved_prefix_has_six_decisions_and_107_rows(self):
        calendar, prefix = self.control()
        self.assertEqual(len(calendar), 107)
        self.assertEqual(len(prefix['decisions']), 6)
        self.assertEqual(len(prefix['executions']), 6)
        self.assertFalse(prefix['original_ledger_numerical_audit_repeated'])
        nav = module.nav_prefix(self.documents['nav'], self.nav_bytes, calendar)
        self.assertEqual(nav['metrics']['return_interval_count'], 106)
        self.assertEqual(Decimal(nav['rows'][-1]['nav_date'][:4]), 2023)

    def test_changed_clock_capital_or_oracle_binding_is_rejected(self):
        for kind in ('clock', 'capital', 'oracle'):
            documents = deepcopy(self.documents)
            if kind == 'clock':
                documents['schedule']['schedule'][2]['execution_date'] = '2023-06-02'
            elif kind == 'capital':
                documents['control']['original_fixed_schedule']['initial_cash_usd'] = 5000
            else:
                documents['oracle']['source_hashes'][str(module.BASE / module.BOUND['control'][0])] = '0' * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.control(documents)

    def test_missing_control_day_or_execution_is_rejected(self):
        for key in ('daily', 'executions'):
            documents = deepcopy(self.documents)
            documents['control']['execution'][key].pop(1)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.control(documents)

    def test_future_nav_date_and_duplicate_csv_are_rejected(self):
        calendar, _ = self.control()
        changed = deepcopy(self.documents['nav'])
        changed['nav']['rows'][0]['nav_date'] = '2023-04-03'
        with self.assertRaises(ValueError):
            module.nav_prefix(changed, self.nav_bytes, calendar)
        lines = self.nav_bytes.splitlines(keepends=True)
        with self.assertRaises(ValueError):
            module.nav_prefix(self.documents['nav'], b''.join(lines + [b'\n', lines[1]]), calendar)

    def test_decimal_context_is_independent_and_denominator_is_fixed(self):
        previous = getcontext().copy()
        try:
            getcontext().prec = 3
            getcontext().traps[Inexact] = True
            result = module.metrics([100 + index for index in range(107)])
            self.assertEqual(Decimal(result['path_return']), Decimal('1.06'))
            self.assertEqual(result['path_max_drawdown'], '0')
        finally:
            setcontext(previous)
        for values in ([1] * 106, [1] * 106 + [True], [1] * 106 + [0]):
            with self.assertRaises(ValueError):
                module.metrics(values)


if __name__ == '__main__':
    unittest.main()
