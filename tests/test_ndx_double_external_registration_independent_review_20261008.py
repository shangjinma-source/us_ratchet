"""External registration construction only; no evaluation or real source loads."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_double_replacement_compressed_worker_20261008 as worker


class Tests(unittest.TestCase):
    def test_missing_and_invalid_anchor_rejected_before_input_io(self):
        with patch.object(worker, 'read', side_effect=AssertionError('Unexpected IO')):
            with self.assertRaises(TypeError):
                worker.execute(registration_path='missing', execute=True)
            for value in (None, '', True, 'a'*63, 'A'*64, 'g'*64, 'a'*64+'\n'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    worker.execute(registration_path='missing', registration_sha256=value, execute=True)

    def test_cli_requires_external_anchor(self):
        result = subprocess.run([sys.executable, '-B', str(worker.SOURCE), '--registration', 'synthetic-not-present', '--execute'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--registration-sha256', result.stderr)
        self.assertIn('required', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_registration_binds_fixed_worker_and_external_hash_reaches_resource_gate(self):
        class ReachedResourceGate(Exception):
            pass
        before = worker.SOURCE.read_bytes()
        worker_sha = hashlib.sha256(before).hexdigest()
        self.assertEqual(worker_sha, worker.LOADED)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = root/'proof.json'
            proof.write_bytes(b'{"synthetic":true}')
            proof_sha = hashlib.sha256(proof.read_bytes()).hexdigest()
            envelope = dict.fromkeys(('max_uncompressed_bytes', 'max_compressed_bytes', 'memory_bytes', 'disk_bytes'), 1)
            output = root/'never-created'
            references = {role:worker.ref(worker.ROOT/path, digest) for role,(path,digest) in worker.BOUND.items()}
            references['lifecycle'] = worker.ref(worker.ROOT/'backtest/ndx_double_replacement_batch_lifecycle_research.py', '1'*64)
            registration = dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_REGISTRATION_V1', input_references=references, worker_reference=worker.ref(worker.SOURCE, worker_sha), domain_counts=worker.COUNTS, flags=worker.FLAGS, output_directory=str(output), resource_envelope=envelope, resource_proof_reference=worker.ref(proof, proof_sha), request_index=0, prior_request_reference=None)
            path = root/'registration.json'
            path.write_bytes(worker.encode(registration))
            external_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.multiple(worker, OUTPUT=output, LIFECYCLE_SHA='1'*64, RESOURCE_PROOF_SHA=proof_sha, RESOURCE_ENVELOPE=envelope), patch.object(worker, 'resource_gate', side_effect=ReachedResourceGate) as gate:
                with self.assertRaises(ReachedResourceGate):
                    worker.execute(registration_path=path, registration_sha256=external_sha, execute=True)
                gate.assert_called_once_with(envelope, output)
            self.assertFalse(output.exists())
        self.assertEqual(worker.SOURCE.read_bytes(), before)
        self.assertFalse(hasattr(worker, 'REGISTRATION_SHA'))


if __name__ == '__main__':
    unittest.main()
