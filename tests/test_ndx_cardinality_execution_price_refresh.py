from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from data.versioning import file_sha256
from scripts.ndx_cardinality_execution_price_refresh import (
    INCUMBENT,
    _verified_reuse_rows,
    _with_control_tickers,
)


class CardinalityExecutionPriceRefreshTests(unittest.TestCase):
    def test_incumbent_controls_are_explicitly_added_without_replacing_candidates(self):
        tickers = _with_control_tickers(
            ["AMAT", "CDNS"],
            include_incumbent_controls=True,
            include_lifecycle_controls=False,
        )
        self.assertTrue(set(INCUMBENT).issubset(tickers))
        self.assertTrue({"AMAT", "CDNS"}.issubset(tickers))

    def test_control_sets_remain_opt_in(self):
        self.assertEqual(
            _with_control_tickers(
                ["AMAT"],
                include_incumbent_controls=False,
                include_lifecycle_controls=False,
            ),
            ["AMAT"],
        )

    def test_reuse_requires_verified_execution_only_data_and_sidecar(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "AMAT.csv"
            raw.write_text(
                "Date,Open,High,Low,Close,Volume\n2024-01-02,100,102,99,101,1000\n",
                encoding="utf-8",
            )
            sidecar = root / "AMAT.csv.manifest.json"
            sidecar.write_text(json.dumps({
                "dataset_key": "AMAT",
                "price_basis": "unadjusted_nominal_trade_price",
                "whole_lot_execution_use_only": True,
                "return_usage_allowed": False,
                "content_sha256": file_sha256(raw),
                "row_count": 1,
                "requested_end": "2024-06-02",
            }), encoding="utf-8")
            inventory = root / "inventory.csv"
            pd.DataFrame([{
                "ticker": "AMAT",
                "status": "FETCHED",
                "rows": 1,
                "path": raw.as_posix(),
                "sha256": file_sha256(raw),
                "sidecar_path": sidecar.as_posix(),
                "sidecar_sha256": file_sha256(sidecar),
                "source_mode": "eastmoney_fqt_0",
            }]).to_csv(inventory, index=False)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_type": "ndx_cardinality_whole_lot_execution_price_bundle",
                "status": "READY",
                "whole_lot_execution_use_only": True,
                "return_engine_cache_modified": False,
                "requested_end": "2024-06-02",
                "artifacts": {
                    "inventory": {
                        "path": inventory.as_posix(),
                        "rows": 1,
                        "sha256": file_sha256(inventory),
                    }
                },
            }), encoding="utf-8")
            rows = _verified_reuse_rows(
                manifest_path.as_posix(), requested_end="2024-06-02"
            )
        self.assertEqual(set(rows), {"AMAT"})
        self.assertEqual(rows["AMAT"]["source_mode"], "verified_reuse:eastmoney_fqt_0")


if __name__ == "__main__":
    unittest.main()
