from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_non_equal_base_inputs as module


class NonEqualBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = module.prepare_non_equal_base_date(
            source_batch='ndx_cardinality_real_runner_p2_exact_v2',
            universe_track='strict_technology', selection_date='2024-02-01')

    def test_real_all_base_tasks_and_independent_ids(self):
        result = self.result
        self.assertEqual(len(result['tasks']), 1369)
        self.assertEqual(result['summary']['non_equal_base_count'], 1369)
        self.assertEqual({r['weight_spec'] for r in result['tasks']}, set(module.SPECS))
        for row in result['tasks']:
            identity = {k: v for k, v in row.items() if k != 'job_id'}
            self.assertEqual(module._sha(identity), row['job_id'])
            self.assertEqual(row['schema_version'], module.SCHEMA)
            self.assertNotIn('return_p50', row)
        self.assertFalse(result['summary']['economic_evaluation_performed'])

    def test_definition_bad_identity_date_spec_and_issuer_rejected(self):
        task = next(row for row in self.result['tasks'] if row['holding_count'] >= 2)
        row = dict(task, portfolio_id=task['source_portfolio_id'], holding_count=str(task['holding_count']))
        child = dict(selection_date=task['selection_date'], universe_track=task['universe_track'],
            training_end=task['decision_data_end'], holding_count=task['holding_count'])
        args = dict(child=child, child_sha=task['source_child_sha256'], csv_sha=task['source_candidates_sha256'],
            source_batch=task['source_batch'], universe_track=task['universe_track'],
            selection_date=task['selection_date'], cutoff=task['decision_data_end'],
            semantics_sha=task['training_semantics_sha256'],
            universe=self.result['inputs']['universe'].set_index('ticker').to_dict('index'))
        for key, value in [('weight_spec', 'FAKE'), ('holding_count', '0'), ('portfolio_id', 'bad'),
                           ('selection_date', '2024-03-01'), ('tickers', 'MISSING')]:
            changed = dict(row, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError): module._definition(changed, **args)
        # Validate duplicate issuer rejection on a two-name real base definition.
        self.assertGreaterEqual(task['holding_count'], 2)
        changed = deepcopy(args); names = task['tickers'].split(';')
        changed['universe'][names[1]]['issuer_id'] = changed['universe'][names[0]]['issuer_id']
        with self.assertRaisesRegex(ValueError, 'issuer'): module._definition(row, **changed)

    def test_loaded_source_guard(self):
        with patch.object(module, '_LOADED', '0'*64):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                module.prepare_non_equal_base_date(source_batch='x', universe_track='x', selection_date='2024-02-01')


if __name__ == '__main__': unittest.main()
