"""Independent attacks on the new reader; no real reconstruction or publication."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_typed_panel_v6_independent_readback_20260925 as m


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {}
        for key, (path, digest) in m.BOUND.items():
            raw = (m.BASE / path).read_bytes()
            assert m.codec.sha(raw) == digest
            cls.documents[key] = m.codec.loads(raw)

    def test_prior_orly_provenance_cannot_be_dropped_or_upgraded(self):
        for attack in ('drop', 'upgrade'):
            documents = deepcopy(self.documents)
            layer = documents['wiring']['v5_extended_provenance']
            if attack == 'drop':
                layer.clear()
            else:
                layer[0]['early_window_local_evidence_available'] = True
            with self.subTest(attack=attack), patch.object(m.codec, 'channel_numbers') as numeric:
                with self.assertRaises(ValueError):
                    m.reconstruct_increment(documents)
                numeric.assert_not_called()

    def test_original_null_registry_and_late_receipt_are_hard_bound(self):
        for attack in ('registry', 'receipt', 'identity'):
            documents = deepcopy(self.documents)
            declaration = documents['wiring']['v6_extended_provenance'][0]['complete_increment_evidence']
            if attack == 'registry':
                declaration['registry_event']['cusip'] = '172908105'
            elif attack == 'receipt':
                declaration['memo_received_at'] = '2026-03-01T00:00:00+00:00'
            else:
                declaration['direct_single_document_cusip_cik_proof'] = True
            with self.subTest(attack=attack), patch.object(m.codec, 'channel_numbers') as numeric:
                with self.assertRaises(ValueError):
                    m.reconstruct_increment(documents)
                numeric.assert_not_called()

    def test_source_conflict_and_existing_output_fail_closed(self):
        path, digest = next(iter(m.LOADED.items()))
        with self.assertRaises(ValueError):
            m.merged_sources({path: '0' * 64})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'independent_increment_readback.json'
            output.write_text('{}', encoding='utf-8')
            with patch.object(m, 'OUTPUT', output), patch.object(m, 'build') as build:
                with self.assertRaises(ValueError):
                    m.publish()
                build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
