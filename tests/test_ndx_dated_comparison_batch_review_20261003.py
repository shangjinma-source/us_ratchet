"""Independent synthetic dispatch-boundary checks; never invoke real stages."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_dated_comparison_batch_20261003 as module
from test_ndx_dated_comparison_batch_20261003 import fixture


class Review(unittest.TestCase):
    def test_predispatch_guard_and_second_stage_guard_partition(self):
        for fail_at, expected_calls in ((2, []), (4, ['comparison'])):
            calls = []
            guard_calls = [0]
            def guard():
                guard_calls[0] += 1
                if guard_calls[0] == fail_at:
                    raise ValueError('Synthetic source drift')
            def comparison(task, references):
                calls.append('comparison')
                return {'path': 'saved', 'sha256': 'a' * 64}
            def reader(*args):
                raise AssertionError('Reader must not dispatch')
            with tempfile.TemporaryDirectory() as directory:
                result = module.execute_queue(['1'*64, '2'*64], initial_rows=[],
                    stage_functions={'comparison': comparison, 'independent_readback': reader},
                    verify_sources=guard, output=Path(directory)/'batch')
                value = json.loads(Path(result['path']).read_bytes())
                self.assertEqual(calls, expected_calls)
                self.assertFalse(value['failure']['current_stage_invoked'])
                self.assertEqual(value['unresolved_task_ids'], ['1'*64] if expected_calls else [])
                self.assertEqual(value['undispatched_task_ids'], ['2'*64] if expected_calls else ['1'*64, '2'*64])

    def test_rejected_saved_audit_retains_both_references_and_blocks_retry(self):
        calls = []
        def stage(task, refs):
            calls.append(task)
            return {'path': str(len(refs)), 'sha256': 'b'*64}
        def validate(task, name, ref, refs):
            if name == 'independent_readback':
                raise ValueError('Saved audit not accepted')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'batch'
            args = dict(initial_rows=[], stage_functions=dict.fromkeys(module.STAGES, stage),
                        verify_sources=lambda: None, output=output, validate_stage=validate)
            result = module.execute_queue(['1'*64, '2'*64], **args)
            value = json.loads(Path(result['path']).read_bytes())
            self.assertEqual(set(value['failure']['completed_stage_references']), set(module.STAGES))
            self.assertEqual(value['new_completed_count'], 0)
            self.assertEqual(calls, ['1'*64, '1'*64])
            with self.assertRaises(ValueError):
                module.execute_queue(['1'*64, '2'*64], **args)

    def test_full_denominator_and_unfinished_parent_cannot_be_shortened(self):
        for mutate in (
            lambda d: d['summary'].update(full_new_cutoff_task_denominator=str(module.FULL)),
            lambda d: d['economic_result'].update(unresolved_task_ids=['1'*64]),
            lambda d: d['economic_result']['new_completed_rows'][-1]['stage_references'].pop('continuous_readback'),
            lambda d: d['initial']['rows'].pop(),
        ):
            docs = fixture()
            mutate(docs)
            with self.assertRaises(ValueError):
                module.validate_queue(**docs)
        with patch.dict(module.PINS, {'economic_reader': ('missing.py', None)}), patch.object(module, 'load_module', side_effect=AssertionError('No imports')):
            with self.assertRaises(ValueError):
                module.run(execute=True)


if __name__ == '__main__':
    unittest.main()
