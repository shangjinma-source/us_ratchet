"""True new capture and observation business IO with a temporary B/C family."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ndx_continuation_observation_fixture_20261009_v1 import physical_continuation_candidate, run_writer, run_reader
from scripts import ndx_continuation_observation_writer_20261009_v1 as writer


class ContinuationObservationTrueChainTests(unittest.TestCase):
    def test_true_sequence73_and_five_file_independent_readback(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_continuation_actual73_') as directory:
            context = physical_continuation_candidate(Path(directory))
            payload_ref, receipt_ref = run_writer(context)
            payload = writer.decode(Path(payload_ref['path']).read_bytes())
            self.assertEqual(payload['sequence'], 73)
            self.assertEqual(payload['session'], '2026-10-13')
            self.assertEqual(payload['first_actual_observed_session_of_month'], '2026-10-02')
            report_ref = run_reader(context, payload_ref, receipt_ref)
            report = writer.decode(Path(report_ref['path']).read_bytes())
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['counts']['parent_typed_row_count'], 72)
            self.assertFalse(report['writer_called'])
            self.assertFalse(report['payload_core_called'])
            self.assertEqual(len(report['reader_input_references']), 13)
            self.assertEqual({item.name for item in Path(payload_ref['path']).parent.iterdir()}, {
                'started.json', 'observation_payload.json', 'receipt.json', 'reader_started.json', 'independent_readback.json'})
            own = report['reader_started_reference_observed_not_external_anchor']
            self.assertEqual(report['source_hashes'][own['path']], own['sha256'])
            self.assertFalse(report['future_independent_oos'])
            self.assertFalse(report['live_mutation_allowed'])


if __name__ == '__main__':
    unittest.main()
