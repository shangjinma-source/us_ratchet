import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_root_price_archive_contract_research as module


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.contract=module.load_contract()

    def test_real_complete_archive_and_partition(self):
        expected={p:r['expected_historical_sha256'] for p,r in self.contract['rows'].items()}
        result=module.verify_expected_sources(expected,self.contract)
        self.assertEqual(len(result['archive_resolutions']),85)
        self.assertEqual(len(result['historical_gap_observations']),26)
        self.assertFalse(set(expected)&set(result['live_verified_source_hashes']))

    def test_future_mutation_of_original_cache_does_not_erase_preserved_bytes(self):
        p,r=next((p,r) for p,r in self.contract['rows'].items() if r['historical_expected_bytes_preserved'])
        original=module.drift.file_sha
        def changed(path):return '0'*64 if str(path) in self.contract['rows'] else original(path)
        with patch.object(module.drift,'file_sha',side_effect=changed):
            raw=module.read_historical_bytes(p,r['expected_historical_sha256'],self.contract)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),r['expected_historical_sha256'])

    def test_gap_cannot_be_read_as_historical_or_new_sha_accepted(self):
        p,r=next((p,r) for p,r in self.contract['rows'].items() if not r['historical_expected_bytes_preserved'])
        with self.assertRaisesRegex(ValueError,'not recovered'):
            module.read_historical_bytes(p,r['expected_historical_sha256'],self.contract)
        with self.assertRaisesRegex(ValueError,'Different old SHA'):
            module.read_historical_bytes(p,r['archived_sha256'],self.contract)
        fake=copy.deepcopy(self.contract);fake['rows'][p]['historical_expected_bytes_preserved']=True
        with self.assertRaisesRegex(ValueError,'hard archive'):
            module.verify_expected_sources({},fake)

    def test_non_inventory_source_remains_strict(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'arbitrary.csv';p.write_bytes(b'old');old=hashlib.sha256(b'old').hexdigest();p.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'strict live source'):
                module.verify_expected_sources({str(p):old},self.contract)

    def test_archived_bytes_drift_rejected(self):
        r=next(iter(self.contract['rows'].values()));original=module.drift.file_sha
        with patch.object(module.drift,'file_sha',side_effect=lambda p:'0'*64 if str(p)==r['archived_path'] else original(p)):
            with self.assertRaises(ValueError):module.verify_expected_sources({},self.contract)


if __name__=='__main__':unittest.main()
