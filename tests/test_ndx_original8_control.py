from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_original8_control import (
    EXPECTED_TICKERS,
    NdxOriginal8ControlError,
    build_original8_control,
    file_sha256,
)


class Original8ControlTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        projection = root / "projection.csv"
        rows = [
            {
                "selection_date": "2024-06-03",
                "ticker": ticker,
                "security_id": f"security:{ticker}",
                "issuer_id": f"issuer:{ticker}",
                "risk_chain": "chain",
            }
            for ticker in EXPECTED_TICKERS
        ]
        pd.DataFrame(rows).to_csv(projection, index=False)
        identity = root / "identity.json"
        identity.write_text(
            json.dumps(
                {
                    "manifest_type": "ndx_incumbent_pit_execution_attribution",
                    "artifacts": {
                        "projection": {
                            "path": projection.as_posix(),
                            "sha256": file_sha256(projection),
                            "rows": len(rows),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        weights = {ticker: 1.0 / len(EXPECTED_TICKERS) for ticker in EXPECTED_TICKERS}
        dynamic = root / "dynamic.json"
        dynamic.write_text(
            json.dumps(
                {
                    "manifest_type": "ndx_dynamic_cardinality_historical_walkforward",
                    "capital_replay_source_coverage": {
                        "original_8_weight_source": "CAPITAL_REPLAY_CHILD_MANIFEST_CONSENSUS",
                        "original_8_incumbent_weights": weights,
                        "original_8_source_state_sha256": "a" * 64,
                    },
                    "inputs": {
                        "incumbent_identity_manifest": {
                            "path": identity.as_posix(),
                            "sha256": file_sha256(identity),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return dynamic, identity

    def test_freezes_complete_identity_weight_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dynamic, identity = self._fixture(root)
            result = build_original8_control(
                root, dynamic_manifest_path=dynamic, identity_manifest_path=identity
            )
            self.assertEqual(result["manifest_type"], "ndx_original_8_frozen_research_control")
            self.assertEqual(len(result["definition"]["securities"]), 8)
            self.assertEqual(result["definition"]["starting_capital_usd"], 25000.0)
            self.assertFalse(result["promotion_allowed"])
            self.assertFalse(any(result["live_mutation"].values()))

    def test_rejects_identity_artifact_hash_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dynamic, identity = self._fixture(root)
            (root / "projection.csv").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxOriginal8ControlError, "hash mismatch"):
                build_original8_control(root, dynamic_manifest_path=dynamic, identity_manifest_path=identity)

    def test_rejects_weight_ticker_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dynamic, identity = self._fixture(root)
            payload = json.loads(dynamic.read_text(encoding="utf-8"))
            weights = payload["capital_replay_source_coverage"]["original_8_incumbent_weights"]
            weights["OTHER"] = weights.pop("NVDA")
            dynamic.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(NdxOriginal8ControlError, "ticker set"):
                build_original8_control(root, dynamic_manifest_path=dynamic, identity_manifest_path=identity)

    def test_rejects_duplicate_issuer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dynamic, identity = self._fixture(root)
            projection = root / "projection.csv"
            frame = pd.read_csv(projection)
            frame.loc[1, "issuer_id"] = frame.loc[0, "issuer_id"]
            frame.to_csv(projection, index=False)
            identity_payload = json.loads(identity.read_text(encoding="utf-8"))
            identity_payload["artifacts"]["projection"]["sha256"] = file_sha256(projection)
            identity.write_text(json.dumps(identity_payload), encoding="utf-8")
            dynamic_payload = json.loads(dynamic.read_text(encoding="utf-8"))
            dynamic_payload["inputs"]["incumbent_identity_manifest"]["sha256"] = file_sha256(identity)
            dynamic.write_text(json.dumps(dynamic_payload), encoding="utf-8")
            with self.assertRaisesRegex(NdxOriginal8ControlError, "not unique"):
                build_original8_control(root, dynamic_manifest_path=dynamic, identity_manifest_path=identity)


if __name__ == "__main__":
    unittest.main()
