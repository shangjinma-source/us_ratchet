"""Mock one BKNG calculation on each side; no actual channel audit/build."""
from copy import deepcopy
from decimal import localcontext, Inexact
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_conditional_panel_v4_20260925 as producer
from scripts import ndx_new_cutoff_typed_panel_v4_independent_readback_20260925 as reader


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {role: reader.codec.loads(Path(reader.ref(role)['path']).read_bytes()) for role in reader.BOUND}
        cls.numbers = ([.01]*126, [20.]*127, dict(volumes=[10000000]*63, dollars=[200000000.]*63, median=200000000.), None)

    def candidate(self):
        with patch.object(producer.core, 'channel_values', return_value=self.numbers) as call:
            value = producer.assemble(self.docs)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[2], 'BKNG')
        value['source_hashes'] = {}
        return value

    def test_independent_full_envelope_matches_with_single_bkng_each(self):
        value = self.candidate()
        with patch.object(reader.codec, 'channel_numbers', return_value=self.numbers) as call:
            decoded = reader.verify_candidate(value, self.docs, {})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0]['ticker'], 'BKNG')
        self.assertEqual(decoded['conditional_security_count'], 22)
        self.assertEqual(value['source_coordinate_candidate_count'], 23)

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
                value['v4_incremental_evidence_and_projection'][0]['early_window_local_evidence_available'] = True
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
