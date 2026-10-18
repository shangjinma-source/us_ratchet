"""CSV identity fields must survive the hash-checked artifact reader exactly."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pandas as pd
from backtest.ndx_dynamic_shadow_candidate_identity_v3 import _optional_date

from backtest.ndx_dynamic_shadow_candidate_generator_v3 import (
    _artifact_csv_bytes, _csv_bytes, NdxDynamicShadowCandidateGeneratorV3Error,
)
from scripts.ndx_dynamic_shadow_candidate_generator_v3 import _csv_bytes as runtime_csv_bytes


class IdentityCsvTests(unittest.TestCase):
    def test_taxonomy_blank_date_does_not_weaken_official_missing_weight(self):
        raw = b"ticker,evidence_available_date,weight\nBLANK,,\nLITERAL,NaN,0.5\n"
        for reader in (_csv_bytes, runtime_csv_bytes):
            with self.subTest(reader=reader.__module__):
                taxonomy = reader(raw, keep_default_na=False)
                self.assertEqual(taxonomy.evidence_available_date.tolist(), ["", "NaN"])
                self.assertIsNone(_optional_date(taxonomy.iloc[0].evidence_available_date, "evidence date"))
                with self.assertRaises(ValueError):
                    _optional_date(taxonomy.iloc[1].evidence_available_date, "evidence date")
                official = reader(raw)
                self.assertTrue(pd.isna(official.iloc[0].weight))

    def test_runtime_and_archive_preserve_numeric_identity_spelling(self):
        raw = b"ticker,cusip,cusips,cik,Close,Volume\nA,000000002,000000002,0000000101,95.5,2000000\nB,000000003,000000003,0000000102,96.5,3000000\n"
        for reader in (_csv_bytes, runtime_csv_bytes):
            with self.subTest(reader=reader.__module__):
                frame = reader(raw)
                self.assertEqual(frame.cusip.tolist(), ["000000002", "000000003"])
                self.assertEqual(frame.cusips.tolist(), ["000000002", "000000003"])
                self.assertEqual(frame.cik.tolist(), ["0000000101", "0000000102"])
                self.assertEqual(frame.Close.tolist(), [95.5, 96.5])
                self.assertEqual(frame.Volume.tolist(), [2000000, 3000000])

    def test_empty_exact_rule_and_literal_nan_remain_distinct(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"ticker,ticker_lifecycle_rule_id,value\nEXACT,,1.25\nFORGED,NaN,2.5\n"
            path = root / "eligible.csv"
            path.write_bytes(raw)
            artifact = dict(filename=path.name, rows=2, sha256=hashlib.sha256(raw).hexdigest())
            frame = _artifact_csv_bytes(root / "manifest.json", artifact, "eligible")
            self.assertEqual(frame.ticker_lifecycle_rule_id.tolist(), ["", "NaN"])
            self.assertEqual(frame.value.tolist(), [1.25, 2.5])
            path.write_bytes(raw.replace(b"EXACT", b"CHANGED"))
            with self.assertRaisesRegex(NdxDynamicShadowCandidateGeneratorV3Error, "artifact hash changed"):
                _artifact_csv_bytes(root / "manifest.json", artifact, "eligible")
