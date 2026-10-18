"""Existing realized batches must retain actual fresh-v4 acceptance evidence."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import fixture_fresh_search_v4_e2e as fixture
import test_ndx_dynamic_shadow_daily_v2 as calendar_fixture
from backtest import ndx_dynamic_shadow_daily_v3 as adapter


class RealizedAcceptanceTests(unittest.TestCase):
    def test_existing_batch_cannot_bypass_missing_or_corrupt_receipt(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            path, watched = fixture.prepare(root)
            fixture.bindings(stack, root, [])
            accepted = adapter.acceptance.execute(path)
            receipt_path = Path(accepted["receipt_path"])
            final = root / adapter.acceptance.SEARCH / "final/2026-10-01/manifest.json"
            engine = adapter.reviewed.v1
            with patch.object(engine, "_system_utc_now", return_value=datetime(2026, 10, 3, 1, tzinfo=timezone.utc)):
                lanes = engine.build_realized_lane_decisions(final, calendar_fixture._sessions())
            realized_root = root / adapter.RUN_RELATIVE.parent / "realized_decisions"
            engine.write_immutable_realized_decisions(realized_root, lanes)
            batch_path = realized_root / "2026-10-01/batch_manifest.json"
            run = {"research_artifacts": {"realized_batch_manifests": {
                "2026-10-01": {"path": batch_path.as_posix(), "sha256": adapter.acceptance.digest(batch_path)}
            }}}
            adapter._verify_realized_acceptance(run, root)
            with self.assertRaisesRegex(ValueError, "inventory is incomplete"):
                adapter._verify_realized_acceptance(
                    {"research_artifacts": {"realized_batch_manifests": {}}}, root)
            saved = receipt_path.with_suffix(".saved")
            receipt_path.rename(saved)
            with self.assertRaises(FileNotFoundError):
                adapter._verify_realized_acceptance(run, root)
            saved.rename(receipt_path)
            receipt_path.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "acceptance schema changed"):
                adapter._verify_realized_acceptance(run, root)
            for source, digest in watched.items():
                self.assertEqual(adapter.acceptance.digest(source), digest)
