from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_giw_event_evidence import (
    NdxGiwEventEvidenceError,
    normalize_giw_export,
)
from data.versioning import file_sha256
from scripts.ndx_giw_event_evidence import import_export


class NdxGiwEventEvidenceTests(unittest.TestCase):
    def test_preserves_matching_rows_without_promoting_removal_date(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "giw.csv"
            pd.DataFrame([
                {"EffectiveDate": "2024-06-24", "Reason": "Spin-off", "IssueSymbol": "ILMN", "NewIssueSymbol": "GRAL", "IndexSymbol": "NDX"},
                {"EffectiveDate": "2024-07-05", "Reason": "Deletion", "IssueSymbol": "GRAL", "NewIssueSymbol": "", "IndexSymbol": "NDX"},
                {"EffectiveDate": "2024-07-05", "Reason": "Deletion", "IssueSymbol": "OTHER", "NewIssueSymbol": "", "IndexSymbol": "NDX"},
            ]).to_csv(path, index=False)
            rows, summary = normalize_giw_export(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(summary["effective_dates"], ["2024-06-24", "2024-07-05"])
            self.assertTrue(summary["manual_action_classification_required"])
            self.assertFalse(summary["exact_removal_date_promoted"])
            self.assertFalse(summary["historical_backtest_allowed"])

    def test_missing_official_fields_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "giw.csv"
            pd.DataFrame([{"Symbol": "GRAL"}]).to_csv(path, index=False)
            with self.assertRaisesRegex(NdxGiwEventEvidenceError, "missing required"):
                normalize_giw_export(path)

    def test_export_without_target_row_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "giw.csv"
            pd.DataFrame([{
                "EffectiveDate": "2024-06-24", "Reason": "Other",
                "IssueSymbol": "ILMN", "IndexSymbol": "NDX",
            }]).to_csv(path, index=False)
            with self.assertRaisesRegex(NdxGiwEventEvidenceError, "no NDX/GRAL"):
                normalize_giw_export(path)

    def test_import_preserves_raw_hash_and_does_not_promote_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "official_giw.csv"
            output = root / "intake"
            pd.DataFrame([{
                "EffectiveDate": "/Date(1719792000000)/",
                "Reason": "Deletion",
                "IssueSymbol": "GRAL",
                "NewIssueSymbol": "",
                "IndexSymbol": "NDX",
                "Comments": "candidate evidence only",
            }]).to_csv(path, index=False)
            source_hash = file_sha256(path)

            manifest = import_export(path, output)

            raw_path = Path(manifest["raw_export_path"])
            rows_path = Path(manifest["normalized_rows_path"])
            sidecar = rows_path.with_suffix(rows_path.suffix + ".manifest.json")
            self.assertTrue(raw_path.exists())
            self.assertEqual(file_sha256(raw_path), source_hash)
            self.assertTrue(rows_path.exists())
            self.assertTrue(sidecar.exists())
            self.assertFalse(manifest["exact_removal_date_promoted"])
            self.assertFalse(manifest["exact_registry_mutation_performed"])
            self.assertFalse(manifest["event_gap_disposition_mutation_performed"])
            sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(sidecar_payload["raw_export_sha256"], source_hash)


if __name__ == "__main__":
    unittest.main()
