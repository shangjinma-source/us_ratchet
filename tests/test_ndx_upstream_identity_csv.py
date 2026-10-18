"""Real upstream CSV readers preserve identifiers without weakening manifests."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import pandas as pd

from data import ndx_history as history
from data import ndx_taxonomy as taxonomy
from data.ndx_history_csv_v2 import read_history_cache
from data.versioning import manifest_path, write_dataset_manifest


class UpstreamIdentityCsvTests(unittest.TestCase):
    def _fixture(self, root, *, history_input=False):
        cfg = SimpleNamespace(cache_dir=root)
        path = history._history_path(cfg) if history_input else root / "crosswalk.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        if history_input:
            rows = [{
                "report_date": "2026-03-31", "filed_date": "2026-05-28",
                "available_date": "2026-05-28", "accession_number": "0001067839-26-000001",
                "ticker": "NA" if i == 0 else f"T{i:03}", "name": f"Issuer {i}",
                "cusip": f"{i + 1:09}", "isin": f"US{i + 1:09}0",
                "weight": .01, "value_usd": 50000000,
                "mapping_method": "fixture", "source_locator": "https://www.sec.gov/fixture",
            } for i in range(100)]
            frame = pd.DataFrame(rows, columns=history.HISTORY_COLUMNS)
        else:
            frame = pd.DataFrame({
                "ticker": ["NA", "AAA"], "cusip": ["000000001", "000000002"],
                "cusips": ["000000001", "000000002"], "cik": ["0000000001", "0000000002"],
                "weight": [.4, .6], "ticker_lifecycle_rule_id": ["", "NaN"],
            })
        frame.to_csv(path, index=False)
        write_dataset_manifest(
            path, dataset_type="ndx_point_in_time_constituents" if history_input else "identity_fixture",
            dataset_key="qqq_nport_public_filings" if history_input else "crosswalk",
            source="test_fixture", row_count=len(frame),
            extra={"historical_backtest_allowed": True, "point_in_time_scope": history.HISTORY_SCOPE,
                   "report_count": 1},
        )
        return path, cfg, frame

    def _read(self, path, cfg, history_input):
        if history_input:
            return read_history_cache(cfg)[0]
        return taxonomy.read_versioned_csv(path, name="fixture", used_for="identity regression")[0]

    def test_taxonomy_identity_lexemes_and_numeric_weights(self):
        with TemporaryDirectory() as directory:
            path, cfg, expected = self._fixture(Path(directory))
            actual = self._read(path, cfg, False)
            for column in ("ticker", "cusip", "cusips", "cik", "ticker_lifecycle_rule_id"):
                self.assertEqual(actual[column].tolist(), expected[column].tolist(), column)
            self.assertTrue(pd.api.types.is_numeric_dtype(actual["weight"]))
            self.assertAlmostEqual(actual["weight"].sum(), 1.)

    def test_history_cusip_lexemes_and_numeric_economics(self):
        with TemporaryDirectory() as directory:
            path, cfg, expected = self._fixture(Path(directory), history_input=True)
            actual = self._read(path, cfg, True)
            self.assertEqual(actual["cusip"].tolist(), expected["cusip"].tolist())
            self.assertEqual(actual["ticker"].iloc[0], "NA")
            for column in ("weight", "value_usd"):
                self.assertTrue(pd.api.types.is_numeric_dtype(actual[column]))
            self.assertAlmostEqual(actual["weight"].sum(), 1.)

    def test_manifest_hash_and_row_count_still_fail_closed(self):
        for history_input in (False, True):
            for corruption in ("hash", "rows"):
                with self.subTest(history=history_input, corruption=corruption), TemporaryDirectory() as directory:
                    path, cfg, _ = self._fixture(Path(directory), history_input=history_input)
                    if corruption == "hash":
                        path.write_bytes(path.read_bytes() + b"\n")
                    else:
                        sidecar = manifest_path(path)
                        payload = json.loads(sidecar.read_text(encoding="utf-8"))
                        payload["row_count"] += 1
                        sidecar.write_text(json.dumps(payload), encoding="utf-8")
                    error = history.NdxHistoryError if history_input else taxonomy.NdxTaxonomyError
                    with self.assertRaisesRegex(error, "hash|row count"):
                        self._read(path, cfg, history_input)


if __name__ == "__main__":
    unittest.main()
