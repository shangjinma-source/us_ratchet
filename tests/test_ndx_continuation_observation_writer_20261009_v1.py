"""Boundary tests; physical observation integration is a separate required test."""
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_continuation_observation_writer_20261009_v1 as writer


class ContinuationObservationWriterBoundaryTests(unittest.TestCase):
    def arguments(self):
        return dict(registration_path='E:/SYNTHETIC_ONLY_registration.json', registration_sha256='a' * 64,
            implementation_pair_binding_path='E:/SYNTHETIC_ONLY_B.json', implementation_pair_binding_sha256='b' * 64,
            consumer_role_registry_path='E:/SYNTHETIC_ONLY_C.json', consumer_role_registry_sha256='c' * 64)

    def test_preview_and_pending_binding_never_read_sources(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Pending runtime must not read sources')):
            self.assertEqual(writer.run(**self.arguments()), {'status': 'NOT_EXECUTED'})
            with self.assertRaisesRegex(ValueError, 'Pending immutable anchor'):
                writer.run(**self.arguments(), execute=True)

    def test_invalid_host_anchor_never_reads_sources(self):
        with patch.object(writer, 'SHARED_ANCESTRY_VERIFIER', (writer.SHARED_ANCESTRY_VERIFIER[0], 'd' * 64)), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('Invalid host anchor must not read sources')):
            args = self.arguments()
            args['consumer_role_registry_path'] = 'E:/../SYNTHETIC_ONLY_C.json'
            with self.assertRaises(ValueError):
                writer.run(**args, execute=True)
            with self.assertRaises(ValueError):
                writer.run(**self.arguments(), execute=1)


if __name__ == '__main__':
    unittest.main()
