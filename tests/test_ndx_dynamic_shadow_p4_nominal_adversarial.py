"""Independent frozen-price byte binding checks; no live data is modified."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from backtest.ndx_dynamic_shadow_p4_gate_v2 import (
    NdxDynamicShadowP4GateV2Error,
    _load_frozen_nominal_snapshot,
    canonical_sha256,
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class FrozenNominalAdversarialTest(unittest.TestCase):
    def fixture(self, root: Path):
        date = "2026-10-01"
        directory = root / "data/cache/research/ndx_dynamic_shadow_daily_v1/nominal_price_evidence" / date
        (directory / "sources").mkdir(parents=True)
        for relative in ("backtest/ndx_dynamic_shadow_daily.py", "scripts/ndx_dynamic_shadow_daily.py"):
            source = root / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"fixture source\n")
        raw = b"Date,ticker,Open,Close\n2026-10-01,TEST,100.0,101.0\n"
        source = directory / "sources/TEST.csv"
        source.write_bytes(raw)
        (directory / "prices.csv").write_bytes(raw)
        manifest = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_nominal_open_close_evidence",
            "status": "IMMUTABLE_EXACT_TICKER_SESSION_GRID",
            "valuation_end_date": date, "tickers": ["TEST"],
            "price_basis": "UNADJUSTED_NOMINAL_TRADE_PRICE",
            "execution_field": "Open", "valuation_field": "Close",
            "sources": {"TEST": {
                "filename": "sources/TEST.csv", "rows": 1, "sha256": digest(raw),
                "source_mode": "SYNTHETIC_FIXTURE", "fallback_errors": [],
                "data_start": date, "data_end": date,
            }},
            "artifact": {"filename": "prices.csv", "rows": 1, "sha256": digest(raw)},
            "module_sha256": digest(b"fixture source\n"),
            "script_sha256": digest(b"fixture source\n"),
            "promotion_allowed": False, "live_mutation": False,
        }
        manifest["manifest_sha256"] = canonical_sha256(manifest)
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        sessions = pd.DataFrame([{
            "session_date": date, "open_timestamp_utc": date + "T13:30:00Z",
            "close_timestamp_utc": date + "T20:00:00Z", "completed": True,
            "is_first_observed_session_of_month": True,
            "origin": "PROSPECTIVE_OBSERVED_APPEND", "decision_eligible": True,
        }])
        return path, source, sessions

    def test_valid_source_is_read_only_and_returns_captured_manifest_digest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, _, sessions = self.fixture(root)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            _, frame, manifest_digest = _load_frozen_nominal_snapshot(path, root=root, sessions=sessions)
            self.assertEqual(manifest_digest, digest(before[path.relative_to(root)]))
            self.assertEqual(frame["Close"].tolist(), [101.0])
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_parsed_source_bytes_cannot_differ_from_hash_checked_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, source, sessions = self.fixture(root)
            original_read = Path.read_bytes
            calls = 0

            def changed_read(value):
                nonlocal calls
                raw = original_read(value)
                if value == source:
                    calls += 1
                    if calls == 1:
                        return raw.replace(b"101.0", b"999.0")
                return raw

            with patch.object(Path, "read_bytes", changed_read):
                with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "source bytes changed"):
                    _load_frozen_nominal_snapshot(path, root=root, sessions=sessions)

    def test_combined_artifact_tamper_and_missing_source_fail_without_recreation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, source, sessions = self.fixture(root)
            artifact = path.parent / "prices.csv"
            artifact.write_bytes(artifact.read_bytes().replace(b"101.0", b"999.0"))
            with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "artifact differs"):
                _load_frozen_nominal_snapshot(path, root=root, sessions=sessions)
            source.unlink()
            with self.assertRaises(FileNotFoundError):
                _load_frozen_nominal_snapshot(path, root=root, sessions=sessions)
            self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
