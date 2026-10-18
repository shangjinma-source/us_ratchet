import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts import ndx_integer_execution_comparison as comparison


class ComparisonWrapperTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range('2022-07-14', periods=5)
        self.path_dates = [str(day.date()) for day in self.dates[1:4]]
        self.weights = {'AAA': .5, 'BBB': .5}
        self.inputs = {
            'nominal_prices': pd.DataFrame({'AAA': [10.] * 5, 'BBB': [20.] * 5}, index=self.dates),
            'returns': pd.DataFrame({'AAA': [.01] * 5, 'BBB': [.02] * 5}, index=self.dates),
            'universe': pd.DataFrame({'ticker': ['AAA', 'BBB'], 'risk_chain': ['A', 'B']}),
            'contract': {**{key: .5 for key in comparison.PARAMETERS},
                         'fit_days': 1, 'step_days': 1, 'portfolio_cash_usd': 5000.,
                         'minimum_cash_buffer_usd': 100., 'transaction_cost_bps': 10.},
        }
        self.context = {'tasks': [{'job_id': 'b' * 64, 'tickers': 'BBB;AAA', 'weight_spec': 'equal_weight'}],
                        'prepared_inputs': {key: key for key in self.inputs}}
        self.context_hash = comparison.encoding._sha(self.context)
        self.raw = json.dumps(self.context).encode()
        self.baseline = {'result': {'whole_lot_return': .1, 'fractional_return': .2},
                         'observation': {'attribution': {'daily': [
                             {'date': day, 'phase': 'REBALANCE_DAY' if index == 0 else 'HOLDING_DAY',
                              'rebalance_target_weights': self.weights if index == 0 else None,
                              'failures': ['WEIGHT_FLOOR'] if index == 1 else []}
                             for index, day in enumerate(self.path_dates)]}}}
        self.calls = []
        self.context_reads = 0

    def execute(self, *, context_drift=False, source_drift=False, watched_drift=False, clock_dates=None):
        original_read = Path.read_bytes
        watched_reads = {}

        def read(path):
            if path.name == 'context.json' and path.parent.name == self.context_hash:
                self.context_reads += 1
                return self.raw + (b' ' if context_drift and self.context_reads > 1 else b'')
            data = original_read(path)
            watched_reads[str(path)] = watched_reads.get(str(path), 0) + 1
            if watched_drift and path.name == 'config.yaml' and watched_reads[str(path)] > 1:
                return data + b' '
            return data

        def simulate(**arguments):
            self.calls.append(arguments)
            return {'selection_policy': arguments['selection_policy'], 'status': 'RESEARCH_ONLY',
                    'daily': [{'date': str(day.date()), 'all_constraints_passed': index != 1}
                              for index, day in enumerate(arguments['prices'].index)]}

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, 'read_bytes', read))
            stack.enter_context(patch.object(comparison, 'observe', return_value=self.baseline))
            stack.enter_context(patch.object(comparison, '_restore_input', side_effect=self.inputs.__getitem__))
            stack.enter_context(patch.object(comparison.runner, 'source_hashes',
                                             side_effect=[{'source': 'original'}, {'source': 'changed' if source_drift else 'original'}]))
            clock_mock = stack.enter_context(patch.object(comparison, 'build_periodic_execution_schedule',
                return_value={'schedule': [{'execution_date': day, 'weights': self.weights}
                                           for day in (self.path_dates if clock_dates is None else clock_dates)]}))
            stack.enter_context(patch.object(comparison, 'simulate_integer_rebalance_research', side_effect=simulate))
            result = comparison.run(self.context_hash, 'b' * 64, domain_radius=2, max_evaluations_per_rebalance=123)
            self.assertEqual(clock_mock.call_args.kwargs['execution_end'], self.path_dates[-1])
            return result

    def test_four_paths_share_exact_dates_and_remain_non_admission(self):
        result = self.execute()
        self.assertEqual(len(self.calls), 4)
        for arguments in self.calls:
            self.assertEqual([str(day.date()) for day in arguments['prices'].index], self.path_dates)
            self.assertEqual(list(arguments['prices']), ['AAA', 'BBB'])
            self.assertEqual(arguments['initial_shares'], {'AAA': 0, 'BBB': 0})
            self.assertEqual(arguments['max_evaluations_per_rebalance'], 123)
        self.assertEqual([len(arguments['schedule']) for arguments in self.calls], [1, 1, 3, 3])
        self.assertEqual([(row['clock'], row['selection_policy']) for row in result['paths']],
            [(clock, policy) for clock in ('LEGACY_STATISTICAL_WINDOW_STARTS', 'PERIODIC_EXECUTION_CLOCK')
             for policy in ('TRACKING_FIRST', 'FEES_FIRST')])
        self.assertEqual(result['day_count'], 3)
        self.assertEqual(result['baseline_floor_risk_failure_days'], 1)
        self.assertEqual(result['baseline_whole_lot_fields'], {'whole_lot_return': .1})
        for row in result['paths']:
            self.assertEqual(row['risk_failure_days'], 1)
            self.assertEqual(row['risk_failures'], [row['first_risk_failure']])
        for flag in ('promotion_allowed', 'order_generation_allowed', 'future_performance_proven'):
            self.assertIs(result[flag], False)

    def test_context_changed_during_comparison_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Comparison sources changed'):
            self.execute(context_drift=True)

    def test_numerical_source_changed_during_comparison_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Comparison sources changed'):
            self.execute(source_drift=True)

    def test_watched_source_changed_during_comparison_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Comparison sources changed'):
            self.execute(watched_drift=True)

    def test_wrong_context_identity_is_rejected_before_simulation(self):
        self.raw = json.dumps({**self.context, 'unexpected': True}).encode()
        with self.assertRaisesRegex(ValueError, 'Context changed after baseline'):
            self.execute()
        self.assertFalse(self.calls)

    def test_missing_interior_price_date_is_not_silently_shortened(self):
        self.inputs['nominal_prices'] = self.inputs['nominal_prices'].drop(self.dates[2])
        with self.assertRaisesRegex(ValueError, 'execution calendar differs'):
            self.execute()
        self.assertFalse(self.calls)

    def test_late_periodic_schedule_is_rejected_before_simulation(self):
        with self.assertRaisesRegex(ValueError, 'must begin on baseline start'):
            self.execute(clock_dates=self.path_dates[1:])
        self.assertFalse(self.calls)

    def test_empty_periodic_schedule_is_rejected_before_simulation(self):
        with self.assertRaisesRegex(ValueError, 'must begin on baseline start'):
            self.execute(clock_dates=[])
        self.assertFalse(self.calls)

    def test_late_legacy_schedule_is_rejected_before_simulation(self):
        days = self.baseline['observation']['attribution']['daily']
        days[0]['phase'] = 'HOLDING_DAY'
        days[1]['phase'] = 'REBALANCE_DAY'
        days[1]['rebalance_target_weights'] = self.weights
        with self.assertRaisesRegex(ValueError, 'must begin on baseline start'):
            self.execute()
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main()
