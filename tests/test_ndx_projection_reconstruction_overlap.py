import copy
import unittest
from unittest.mock import patch

from scripts import ndx_projection_reconstruction_overlap as overlap
from test_ndx_joint_weight_runner import prepared


class ReconstructionOverlapTests(unittest.TestCase):
    def setUp(self):
        self.tasks, _ = prepared()
        self.sources = overlap.runner.source_hashes()
        self.context = {'schema': 'ndx_joint_weight_checkpoint_v1', 'tasks': self.tasks,
                        'numerical_sources': self.sources, 'prepared_inputs': {},
                        'source_evidence': {}, 'runtime': {}}
        self.results = [{**{key: .01 for key in overlap.RETURN_FIELDS + overlap.DRAWDOWN_FIELDS},
                         'tickers': task['tickers'], 'weight_spec': task['weight_spec'],
                         'holding_count': task['holding_count'], 'declared_constraints_passed': False,
                         'whole_lot_executable_all_windows': False, 'constraint_failure_reasons': 'RESEARCH_FAIL'}
                        for task in self.tasks]

    def execute(self, *, checkpoint_changes=None, result_changes=None, source_mix=False,
                evaluation_error=False, snapshot_drift=False):
        context_hash = overlap.encoding._sha(self.context)
        previous = {**self.results[0], **(result_changes or {})}
        checkpoint = {'context_sha256': context_hash, 'task': self.tasks[0], 'status': 'EVALUATED',
                      'result': overlap.encoding._normalize(previous), **(checkpoint_changes or {})}
        checkpoint['checkpoint_sha256'] = overlap.encoding._sha(checkpoint)
        files = {'context.json': self.context, self.tasks[0]['job_id'] + '.json': checkpoint}
        if not self.context['tasks']:
            files = {'context.json': self.context}
        observed = []
        for index, result in enumerate(self.results):
            observed.append({'source_hashes': {'research': 'different' if index and source_mix else 'same'},
                             'original_numerical_sources': self.sources, 'current_runtime': {'python': 'test'},
                             'result': result, 'reconstruction_attempts': []})
        if evaluation_error:
            observed[1] = ValueError('numerical computation unresolved')
        with patch.object(overlap, 'Snapshot') as snapshot_type, \
                patch.object(overlap, 'probe', side_effect=observed) as probe:
            snapshot = snapshot_type.return_value
            snapshot.read.side_effect = lambda path: copy.deepcopy(files[path.name])
            snapshot.directory.return_value = set(files)
            if snapshot_drift:
                snapshot.verify.side_effect = ValueError('snapshot changed')
            result = overlap.run(context_hash)
            self.probe_calls = probe.call_count
            return result

    def test_existing_and_missing_results_are_both_recomputed(self):
        result = self.execute()
        self.assertEqual((result['planned'], result['evaluated'], self.probe_calls), (2, 2, 2))
        self.assertIs(result['rows'][0]['previous_result_exactly_unchanged'], True)
        self.assertIsNone(result['rows'][1]['previous_result_exactly_unchanged'])
        self.assertFalse(result['old_results_reused'])
        self.assertFalse(result['promotion_allowed'])

    def test_mixed_research_sources_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Mixed evaluation sources'):
            self.execute(source_mix=True)

    def test_computation_error_is_not_reported_as_negative_result(self):
        with self.assertRaisesRegex(ValueError, 'numerical computation unresolved'):
            self.execute(evaluation_error=True)

    def test_snapshot_changes_at_end_rejected(self):
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            self.execute(snapshot_drift=True)

    def test_resigned_extra_checkpoint_field_rejected(self):
        with self.assertRaises(ValueError):
            self.execute(checkpoint_changes={'unrecognized': True})

    def test_resigned_boolean_metric_rejected(self):
        with self.assertRaises(ValueError):
            self.execute(result_changes={overlap.RETURN_FIELDS[0]: True})

    def test_resigned_wrong_result_portfolio_rejected(self):
        with self.assertRaises(ValueError):
            self.execute(result_changes={'tickers': 'WRONG'})

    def test_empty_task_denominator_rejected(self):
        self.context['tasks'] = []
        with self.assertRaises(ValueError):
            self.execute()


if __name__ == '__main__':
    unittest.main()
