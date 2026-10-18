from copy import deepcopy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_root_price_archive_contract_research as archive


class IndependentArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = archive.load_contract()

    def test_current_gap_bytes_never_resolve_under_old_or_new_hash(self):
        path, row = next((p, r) for p, r in self.contract['rows'].items() if not r['historical_expected_bytes_preserved'])
        result = archive.verify_expected_sources({path: row['expected_historical_sha256']}, self.contract)
        self.assertEqual(result['archive_resolutions'], [])
        self.assertFalse(result['historical_gap_observations'][0]['historical_bytes_recovered'])
        self.assertFalse(result['historical_full_source_closure_recovered'])
        with self.assertRaisesRegex(ValueError, 'Different old SHA'):
            archive.verify_expected_sources({path: row['archived_sha256']}, self.contract)
        fake = deepcopy(self.contract)
        fake['rows'][path]['archived_sha256'] = row['expected_historical_sha256']
        fake['rows'][path]['historical_expected_bytes_preserved'] = True
        with self.assertRaisesRegex(ValueError, 'hard archive authority'):
            archive.verify_expected_sources({path: row['expected_historical_sha256']}, fake)

    def test_all_original_root_paths_can_disappear_without_false_live_claim(self):
        original = archive.drift.file_sha
        def missing_root(path):
            return None if str(path) in self.contract['rows'] else original(path)
        expected = {p: r['expected_historical_sha256'] for p, r in self.contract['rows'].items()}
        with patch.object(archive.drift, 'file_sha', side_effect=missing_root):
            result = archive.verify_expected_sources(expected, self.contract)
            path, row = next((p, r) for p, r in self.contract['rows'].items() if r['historical_expected_bytes_preserved'])
            raw = archive.read_historical_bytes(path, row['expected_historical_sha256'], self.contract)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), row['expected_historical_sha256'])
        self.assertEqual((len(result['archive_resolutions']), len(result['historical_gap_observations'])), (85, 26))
        self.assertTrue(all(r['original_live_path_verified'] is False for r in result['archive_resolutions'] + result['historical_gap_observations']))
        self.assertFalse(set(expected) & set(result['live_verified_source_hashes']))

    def test_immutable_exact_and_gap_archive_tampering_both_rejected(self):
        original = archive.drift.file_sha
        for exact in (True, False):
            row = next(r for r in self.contract['rows'].values() if r['historical_expected_bytes_preserved'] is exact)
            with patch.object(archive.drift, 'file_sha', side_effect=lambda p: '0' * 64 if str(p) == row['archived_path'] else original(p)):
                with self.assertRaises(ValueError):
                    archive.verify_expected_sources({}, self.contract)

    def test_final_byte_read_rejects_change_after_verification(self):
        path, row = next((p, r) for p, r in self.contract['rows'].items() if r['historical_expected_bytes_preserved'])
        # Inject a race only after the validation boundary; no research file is modified.
        with patch.object(archive, 'verify_expected_sources', return_value={'archive_resolutions': [row]}):
            with patch.object(Path, 'read_bytes', return_value=b'changed after successful verification'):
                with self.assertRaisesRegex(ValueError, 'changed during byte read'):
                    archive.read_historical_bytes(path, row['expected_historical_sha256'], self.contract)


if __name__ == '__main__':
    unittest.main()
