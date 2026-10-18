"""Mock one CTAS calculation on each side; no actual channel audit/build."""
from copy import deepcopy
from decimal import localcontext, Inexact
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_conditional_panel_v6_20260925 as producer
from scripts import ndx_new_cutoff_typed_panel_v6_independent_readback_20260925 as reader


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {role: reader.codec.loads(Path(reader.ref(role)['path']).read_bytes()) for role in reader.BOUND}
        cls.numbers = ([.01]*126, [20.]*127, dict(volumes=[10000000]*63, dollars=[200000000.]*63, median=200000000.), None)

    def candidate(self):
        with patch.object(producer.core, 'channel_values', return_value=self.numbers) as call:
            value = producer.assemble(self.docs)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[2], 'CTAS')
        value['source_hashes'] = {}
        return value

    def test_printed_date_is_not_joint_availability(self):
        for attack in ('date_role', 'sidecar'):
            value = self.candidate()
            if attack == 'sidecar':
                value['v6_incremental_evidence_and_projection'][0]['dated_anchor_role'] = 'JOINT_AVAILABILITY'
            else:
                panel = reader.codec.decode_frames(value['panel'])
                fact = reader.one(panel['observed_provenance_and_missing'], 'CTAS')['coordinate_assumption']['dated_fact']
                fact['date_role'] = 'JOINT_AVAILABILITY'
                panel['panel_content_sha256'] = reader.codec.checksum(panel)
                value['panel'] = reader.codec.encode_frames(panel)
            with self.subTest(attack=attack), patch.object(reader.codec, 'channel_numbers', return_value=self.numbers):
                with self.assertRaises(ValueError): reader.verify_candidate(value, self.docs, {})

    def test_source_boundary_errors_before_numeric_reconstruction(self):
        for attack in ('multipart', 'receipt', 'option'):
            docs = deepcopy(self.docs)
            d = docs['wiring']['v6_extended_provenance'][0]['complete_increment_evidence']
            if attack == 'multipart': d['complete_capture_evidence']['original_body_is_pdf_without_multipart'] = True
            elif attack == 'receipt': d['memo_received_at'] = '2024-08-21'
            else: d['complete_memo_evidence']['option_deliverable_is_not_equity_identity_proof'] = False
            with self.subTest(attack=attack), patch.object(reader.codec, 'channel_numbers') as numbers:
                with self.assertRaises(ValueError): reader.reconstruct_increment(docs)
                numbers.assert_not_called()

    def test_five_hard_parents_and_pending_anchors(self):
        for role in reader.BOUND:
            r = reader.ref(role)
            self.assertEqual(reader.codec.sha(Path(r['path']).read_bytes()), r['sha256'])
        with patch.object(reader, 'PRODUCER_SHA', None), patch.object(reader.Path, 'read_bytes') as read:
            with self.assertRaises(ValueError): reader.build()
            read.assert_not_called()

    def test_independent_full_envelope_matches_with_single_ctas_each(self):
        value = self.candidate()
        with patch.object(reader.codec, 'channel_numbers', return_value=self.numbers) as call:
            decoded = reader.verify_candidate(value, self.docs, {})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0]['ticker'], 'CTAS')
        self.assertEqual(decoded['conditional_security_count'], 24)
        self.assertEqual(value['source_coordinate_candidate_count'], 25)

    def test_rechecksummed_gap_and_v3_evidence_changes_rejected(self):
        for attack in ('gap', 'sidecar', 'local_early'):
            value = self.candidate()
            if attack == 'gap':
                panel = reader.codec.decode_frames(value['panel'])
                reader.one(panel['observed_provenance_and_missing'], 'CRWD')['blocking_reasons'] = []
                panel['panel_content_sha256'] = reader.codec.checksum(panel)
                value['panel'] = reader.codec.encode_frames(panel)
            elif attack == 'sidecar':
                value['v3_incremental_evidence_and_projection'][0]['original_gap'] = {}
            else:
                value['v6_incremental_evidence_and_projection'][0]['early_window_local_evidence_available'] = True
            with self.subTest(attack=attack), patch.object(reader.codec, 'channel_numbers', return_value=self.numbers):
                with self.assertRaises(ValueError): reader.verify_candidate(value, self.docs, {})

    def test_producer_context_and_old_frame_dtype(self):
        def calculate(*args):
            from decimal import getcontext
            self.assertEqual(getcontext().prec, 80)
            self.assertFalse(getcontext().traps[Inexact])
            return self.numbers
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = True
            with patch.object(producer.core, 'channel_values', side_effect=calculate):
                producer.assemble(self.docs)
        before = producer.codec.typed_decode(self.docs['parent_panel']['panel'])
        after = deepcopy(before)
        ticker = after['raw_volume'].columns[0]
        after['raw_volume'][ticker] = after['raw_volume'][ticker].astype('float64')
        with self.assertRaises(ValueError): producer.original_frame_proof(before, after)


if __name__ == '__main__':
    unittest.main()
