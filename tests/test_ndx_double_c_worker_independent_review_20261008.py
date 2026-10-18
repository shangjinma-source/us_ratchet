import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_double_replacement_c_stream_worker_20261008 as worker
import test_ndx_double_c_stream_worker_20261008 as fixtures


class Tests(unittest.TestCase):
    def test_resource_loss_after_return_still_preserves_raw_before_next_stop(self):
        fixture = fixtures.Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration, constants = fixture.fixture(root)
            calls = root / 'code/synthetic_calls.jsonl'
            observed = []
            def gate(*args, **kwargs):
                observed.append((kwargs.get('phase', 'batch'), calls.exists()))
                if calls.exists():
                    raise ValueError('RESOURCE_STOP_BEFORE_DISPATCH_MEMORY')
            with patch.multiple(worker, **constants), patch.object(worker, 'resource_gate', side_effect=gate):
                result_ref = worker.execute(registration_path=registration['path'], registration_sha256=registration['sha256'], execute=True)
            result = json.loads(Path(result_ref['path']).read_bytes())
            batch = root / 'output/batches/000/000000000'
            self.assertTrue((batch / 'raw_return.json.gz').is_file())
            self.assertTrue((batch / 'raw_receipt.json').is_file())
            self.assertTrue((batch / 'inspection.json').is_file())
            self.assertTrue((batch / 'result.json').is_file())
            self.assertEqual(result['inspection']['counts']['undispatched'], 1)
            self.assertEqual(result['inspection']['counts']['inspected_feasible'] + result['inspection']['counts']['inspected_infeasible'], 512)
            self.assertEqual(result['evaluator_call_count'], 1)
            self.assertEqual(len(calls.read_text().splitlines()), 1)
            self.assertEqual(observed[-1], ('remaining', True))
            self.assertFalse((root / 'output/publication.json').exists())


if __name__ == '__main__':
    unittest.main()
