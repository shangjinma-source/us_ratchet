"""Independent bounded streaming and failure checks, synthetic documents only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_dated_comparison_results_summary_20261003 as module
from backtest import ndx_dated_comparison_results_summary_research as core
from test_ndx_dated_comparison_results_summary_research import fixture, saved


class Review(unittest.TestCase):
    def test_each_stratum_preserved_and_only_supplied_documents_loaded(self):
        args = fixture()
        for i, task in enumerate(args['task_summary']['rows']):
            if i % 32 == 1:
                args['comparisons_by_task'][task['numerical_task_id']] = saved(task, missing=(i % 64 == 1))
        before = deepcopy(args)
        calls = []
        def load(task, references):
            calls.append(task)
            return deepcopy(args['comparisons_by_task'][task])
        result = module.stream_summary(args['task_summary'], args['task_summary_reference'],
            dict.fromkeys(args['comparisons_by_task'], {}), load, core)
        self.assertEqual(result, core.summarize_comparisons(**args))
        self.assertEqual(args, before)
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(len(calls), 51)
        self.assertEqual(len(result['rows']), 1632)
        for stratum in result['k_spec_coverage']:
            self.assertEqual(stratum['planned_task_count'], 32)
            self.assertEqual(stratum['supplied_comparison_count'], 1)
            self.assertEqual(stratum['not_supplied_count'], 31)

    def test_source_collision_and_foreign_id_are_not_ignored(self):
        args = fixture()
        task = args['task_summary']['rows'][1]
        envelope = saved(task)
        envelope['audit_reference'] = dict(path=envelope['document_reference']['path'], sha256='f'*64)
        with self.assertRaises(ValueError):
            module.stream_summary(args['task_summary'], args['task_summary_reference'],
                {task['numerical_task_id']: {}}, lambda *unused: envelope, core)
        with self.assertRaises(ValueError):
            module.stream_summary(args['task_summary'], args['task_summary_reference'],
                {'f'*64: {}}, lambda *unused: self.fail('Must reject before loading'), core)

    def test_item_failure_preserves_started_without_success_and_blocks_retry(self):
        args = fixture()
        task = args['task_summary']['rows'][1]
        docs = dict(task_summary=args['task_summary'], batch=dict(failure=None, unresolved_task_ids=[], undispatched_task_ids=[]))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'summary'
            with patch.object(module, 'OUTPUT', output), patch.object(module, 'load_inputs',
                    return_value=(docs, {task['numerical_task_id']: {}}, {}, core)), \
                    patch.object(module, 'guard'), patch.object(module, 'extract_item', side_effect=ValueError('Changed current audit bytes')):
                with self.assertRaises(ValueError):
                    module.run(execute=True)
                self.assertEqual({path.name for path in output.iterdir()}, {'started.json', 'failure.json'})
                with self.assertRaises(ValueError):
                    module.run(execute=True)


if __name__ == '__main__':
    unittest.main()
