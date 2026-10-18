"""Independent authentic-artifact preservation and bounded-read checks."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_cash_history_dashboard as dashboard


class CashHistoryRootIndependentTests(unittest.TestCase):
    def test_all_original_rows_preserved_and_result_detached(self):
        original = json.loads(dashboard.BOUND['projection'][0].read_bytes())
        result = dashboard.read_cash_history_evidence()
        restored = copy.deepcopy(result['rows'])
        for row in restored:
            for group in ('metrics', 'differences'):
                for metric in row[group]:
                    metric.pop('display')
        self.assertEqual(original['rows'], restored)
        self.assertEqual(original['limitations'], result['limitations'])
        self.assertEqual(40, result['scenario_count'])
        result['rows'][0]['buys'].clear()
        again = dashboard.read_cash_history_evidence()
        self.assertEqual(original['rows'][0]['buys'], again['rows'][0]['buys'])
        self.assertFalse(again['current_cash_input_consumed'])
        self.assertFalse(again['full_transitive_source_closure_reverified'])
        self.assertFalse(again['formal_dual_benchmark_admission'])

    def test_only_fixed_eight_paths_read_not_saved_transitive_claims(self):
        allowed = {path for path, _ in dashboard.BOUND.values()}
        observed = set()
        original_read = Path.read_bytes

        def guarded(path):
            self.assertIn(path, allowed, 'Unbounded source-claim read')
            observed.add(path)
            return original_read(path)

        with patch.object(Path, 'read_bytes', guarded):
            self.assertTrue(dashboard.read_cash_history_evidence()['available'])
        self.assertEqual(allowed, observed)

    def test_new_independent_audit_failure_rejected_before_read(self):
        self.assertTrue(dashboard.read_cash_history_evidence()['available'])
        original_listing = Path.iterdir

        def changed(path):
            values = list(original_listing(path))
            if path == dashboard.AUDIT:
                values.append(path / 'failure.json')
            return iter(values)

        with patch.object(Path, 'iterdir', changed), patch.object(
                Path, 'read_bytes', side_effect=AssertionError('Read after failed audit')):
            with self.assertRaisesRegex(ValueError, 'namespace'):
                dashboard.read_cash_history_evidence()


if __name__ == '__main__':
    unittest.main()
