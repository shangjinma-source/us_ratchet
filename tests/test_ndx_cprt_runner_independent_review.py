"""Mock-only single attempt failure evidence; no actual preflight or fitter."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_cprt_single_task_20260925 as m


class Review(unittest.TestCase):
    def test_orphan_during_fit_preserves_raw_and_blocks_postflight(self):
        taskid = 'a'*64
        identity = dict(weight_spec='equal_weight', cutoff='2026-09-21', selected={},
                        requested_previous_target_weights=None, parameters={})
        state = dict(task={'numerical_identity': identity}, returns=None, source_hashes={}, runtime={})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def fake(**kwargs):
                (root/taskid/'unexpected.json').write_text('{}')
                return {'complete_return': True}
            with patch.object(m, 'OUTPUT_ROOT', root), patch.object(m, 'preflight', return_value=state), patch.object(m, 'guard'), patch.object(m, 'runtime', return_value={}), patch.object(m.fitter, 'refit_dynamic_cutoff_weights', side_effect=fake) as fit, patch.object(m, 'postflight') as post:
                m.run(taskid, execute=True)
                fit.assert_called_once()
                post.assert_not_called()
            raw = json.loads((root/taskid/'raw.json').read_bytes())
            self.assertEqual(raw['fitted'], {'complete_return': True})
            self.assertEqual(raw['returned_fit_count'], 1)
            self.assertIsNone(raw['internal_optimizer_call_count'])
            result = json.loads((root/taskid/'postcheck.json').read_bytes())
            self.assertEqual(result['status'], 'NUMERICAL_OR_VALIDATION_FAILURE')

    def test_all_three_namespaces_refuse_before_inputs(self):
        for name in ('OUTPUT_ROOT', 'OLD_OUTPUT_ROOT', 'MULTIK_OUTPUT_ROOT'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                taskid = 'b'*64
                (Path(folder)/taskid).mkdir()
                with patch.object(m, name, Path(folder)), patch.object(m, 'guard') as guard, patch.object(m.fitter, '_sources') as sources:
                    with self.assertRaises(ValueError):
                        m.preflight(taskid)
                    guard.assert_not_called()
                    sources.assert_not_called()

    def test_guard_rejects_loaded_conflict_before_disk(self):
        path, digest = next(iter(m.LOADED.items()))
        with patch.object(m.Path, 'read_bytes', side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):
                m.guard({path: '0'*64 if digest != '0'*64 else '1'*64})

    def test_execute_integer_refuses_before_preflight(self):
        with patch.object(m, 'preflight') as preflight:
            with self.assertRaises(ValueError):
                m.run('a'*64, execute=1)
            preflight.assert_not_called()


if __name__ == '__main__':
    unittest.main()
