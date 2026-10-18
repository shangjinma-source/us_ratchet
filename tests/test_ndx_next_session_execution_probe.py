import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_next_session_execution_probe as probe
from test_ndx_joint_weight_runner import prepared


class NextSessionProbeTests(unittest.TestCase):
    def fixture(self):
        tasks, inputs = prepared()
        numerical = probe.runner.source_hashes()
        context = dict(tasks=tasks, numerical_sources=numerical,
                       prepared_inputs={key: key for key in inputs})
        digest = probe.encoding._sha(context)
        source_paths = (
            'scripts/ndx_integer_execution_comparison.py', 'scripts/ndx_whole_lot_failure_probe.py',
            'scripts/ndx_joint_weight_verify.py', 'scripts/ndx_joint_weight_progress.py',
            'backtest/ndx_periodic_execution_clock.py', 'backtest/ndx_integer_allocation_research.py',
            'backtest/ndx_integer_rebalance_research.py', 'config/config.yaml',
            'data/state.json', 'data/broker_positions.json')
        sources = {str(probe.ROOT / name): hashlib.sha256((probe.ROOT / name).read_bytes()).hexdigest()
                   for name in source_paths}
        dates = inputs['nominal_prices'].index[:3]
        names = tasks[0]['tickers'].split(';')
        comparison = dict(schema='ndx_integer_execution_comparison_v1', numerical_sources=numerical,
            source_hashes=sources, context_sha256=digest, job_id=tasks[0]['job_id'],
            date_start=str(dates[0].date()), date_end=str(dates[-1].date()), day_count=3,
            periodic_clock={'schedule': [{'execution_date': str(dates[0].date()),
                                          'weights': {name: 1 / len(names) for name in names}}]})
        return comparison, context, inputs

    def execute(self, change=None, *, context_drift=False):
        comparison, context, inputs = self.fixture()
        if change:
            change(comparison)
        raw = json.dumps(comparison).encode()
        context_raw = json.dumps(context).encode()
        original_read = Path.read_bytes
        context_reads = 0
        def read(path):
            nonlocal context_reads
            if path.name == 'synthetic_comparison_for_test.json':
                return raw
            if path.name == 'context.json' and path.parent.name == comparison['context_sha256']:
                context_reads += 1
                return context_raw + (b' ' if context_drift and context_reads > 1 else b'')
            return original_read(path)
        with patch.object(Path, 'read_bytes', read), \
                patch.object(probe, '_restore_input', side_effect=inputs.__getitem__), \
                patch.object(probe, 'simulate_next_session_execution_research', side_effect=lambda **kwargs: {
                    'selection_policy': kwargs['selection_policy'], 'external_execution_calendar_verified': False,
                    'promotion_allowed': False, 'order_generation_allowed': False}) as simulation:
            result = probe.run('synthetic_comparison_for_test.json', hashlib.sha256(raw).hexdigest())
            self.calls = simulation.call_args_list
            return result

    def test_wrong_hash_rejected_before_parsing(self):
        with patch.object(Path, 'read_bytes', return_value=b'not json'), \
                patch.object(probe.json, 'loads', side_effect=AssertionError('must not parse')):
            with self.assertRaisesRegex(ValueError, 'artifact identity differs'):
                probe.run('unused', '0' * 64)

    def test_resigned_missing_source_binding_rejected(self):
        def remove(comparison):
            comparison['source_hashes'].pop(next(iter(comparison['source_hashes'])))
        with self.assertRaisesRegex(ValueError, 'Incomplete comparison source binding'):
            self.execute(remove)

    def test_resigned_late_start_rejected(self):
        def delay(comparison):
            comparison['periodic_clock']['schedule'][0]['execution_date'] = comparison['date_end']
        with self.assertRaisesRegex(ValueError, 'Schedule must begin on comparison start'):
            self.execute(delay)

    def test_two_policies_same_interval_without_external_calendar_claim(self):
        result = self.execute()
        self.assertEqual([row['selection_policy'] for row in result['paths']], ['TRACKING_FIRST', 'FEES_FIRST'])
        self.assertEqual(len(self.calls), 2)
        for call in self.calls:
            self.assertEqual(len(call.kwargs['prices']), 3)
            self.assertTrue(call.kwargs['execution_calendar'].equals(call.kwargs['prices'].index))
        self.assertTrue(all(row['external_execution_calendar_verified'] is False for row in result['paths']))
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['order_generation_allowed'])

    def test_context_change_after_replay_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Input context changed'):
            self.execute(context_drift=True)


if __name__ == '__main__':
    unittest.main()
