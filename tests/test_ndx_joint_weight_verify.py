import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_joint_weight_runner as runner
from scripts.ndx_joint_weight_verify import verify_context
from test_ndx_joint_weight_runner import prepared


class JointWeightVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        tasks, inputs = prepared()
        with patch.object(runner, 'CHECKPOINT_ROOT', Path(self.temporary.name)):
            self.result = runner.run_joint_weight_tasks(tasks, prepared_inputs=inputs,
                                                       source_evidence={'kind': 'synthetic'})
        self.directory = Path(self.result['output_dir'])

    def verify(self):
        return verify_context(self.directory, expected_context_sha256=self.result['context_sha256'])

    def test_actual_checkpoint_economic_recomputation(self):
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        result = self.verify()
        self.assertEqual(result['checked'], 2)
        self.assertFalse(result['source_authenticity_verified'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_resigned_economic_result_is_rejected(self):
        path = next(p for p in self.directory.glob('*.json') if p.name != 'context.json')
        value = json.loads(path.read_bytes())
        value['result']['mapping']['whole_lot_terminal_value_usd'] = {'float_hex': (999999.).hex()}
        value.pop('checkpoint_sha256')
        value['checkpoint_sha256'] = runner._sha(value)
        path.write_bytes(runner._json_bytes(value))
        tampered = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'does not recompute'):
            self.verify()
        self.assertEqual(path.read_bytes(), tampered)

    def test_wrong_expected_identity_and_missing_result_rejected(self):
        with self.assertRaises(ValueError):
            verify_context(self.directory, expected_context_sha256='a' * 64)
        next(p for p in self.directory.glob('*.json') if p.name != 'context.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.verify()

    def test_resigned_boolean_to_integer_result_is_not_exact(self):
        path = next(p for p in self.directory.glob('*.json') if p.name != 'context.json')
        value = json.loads(path.read_bytes())
        value['result']['mapping']['declared_constraints_passed'] = int(
            value['result']['mapping']['declared_constraints_passed'])
        value.pop('checkpoint_sha256')
        value['checkpoint_sha256'] = runner._sha(value)
        path.write_bytes(runner._json_bytes(value))
        with self.assertRaisesRegex(ValueError, 'does not recompute'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
