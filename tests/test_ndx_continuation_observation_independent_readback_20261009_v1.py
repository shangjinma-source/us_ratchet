"""Fail-closed boundaries; true five-file readback is separately required."""
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ndx_continuation_observation_independent_readback_20261009_v1 as reader


class ContinuationObservationReaderBoundaryTests(unittest.TestCase):
    def arguments(self):
        return dict(registration_path='E:/SYNTHETIC_ONLY_registration.json', registration_sha256='a' * 64,
            payload_reference=dict(path='E:/SYNTHETIC_ONLY_writer/observation_payload.json', sha256='b' * 64),
            receipt_reference=dict(path='E:/SYNTHETIC_ONLY_writer/receipt.json', sha256='c' * 64),
            implementation_pair_binding_path='E:/SYNTHETIC_ONLY_B.json', implementation_pair_binding_sha256='d' * 64,
            consumer_role_registry_path='E:/SYNTHETIC_ONLY_C.json', consumer_role_registry_sha256='e' * 64)

    def test_pending_pin_and_preview_never_read_sources(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No pending source reads')):
            self.assertEqual(reader.readback(**self.arguments()), {'status': 'NOT_EXECUTED'})
            with self.assertRaisesRegex(ValueError, 'Pending immutable anchor'):
                reader.readback(**self.arguments(), execute=True)

    def test_payload_alias_rejected_before_any_io(self):
        args = self.arguments()
        args['payload_reference']['path'] = 'E:/SYNTHETIC_ONLY_writer/../trap.json'
        with patch.object(reader, 'SHARED_ANCESTRY_VERIFIER', (reader.SHARED_ANCESTRY_VERIFIER[0], 'f' * 64)), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('No malformed reference reads')):
            with self.assertRaises(ValueError):
                reader.readback(**args, execute=True)


if __name__ == '__main__':
    unittest.main()
