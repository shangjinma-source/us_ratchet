"""Real fresh-search receipts protect daily4 final reads and historical batches."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import fixture_fresh_search_v4_e2e as fixture
import test_ndx_dynamic_shadow_daily_v2 as calendar_fixture
from backtest import ndx_dynamic_shadow_daily as math_engine
from scripts import ndx_dynamic_shadow_daily_v4 as daily


class Daily4RealGuardTests(unittest.TestCase):
    def test_real_receipt_and_existing_batch_count(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            path, watched = fixture.prepare(root)
            fixture.bindings(stack, root, [])
            stack.enter_context(patch.object(daily, "ROOT", root))
            accepted = fixture.acceptance.execute(path)
            receipt = Path(accepted["receipt_path"])
            final = root / fixture.acceptance.SEARCH / "final/2026-10-01/manifest.json"
            self.assertEqual(daily.verify_accepted_final(final), accepted["receipt"])
            outside = root / "other-final.json"
            outside.write_bytes(final.read_bytes())
            with self.assertRaises(ValueError):
                daily.verify_accepted_final(outside)
            with patch.object(math_engine, "_system_utc_now", return_value=datetime(2026, 10, 3, 1, tzinfo=timezone.utc)):
                lanes = math_engine.build_realized_lane_decisions(final, calendar_fixture._sessions())
            realized = root / "data/cache/research/ndx_dynamic_shadow_daily_v1/realized_decisions"
            math_engine.write_immutable_realized_decisions(realized, lanes)
            self.assertEqual(daily.verified_realized_batch_count(), 1)
            stack.enter_context(patch.object(daily.engine, "REALIZED_ROOT", realized))
            stack.enter_context(patch.object(daily.engine, "DISPOSITION_LEDGER", root / "missing-dispositions.jsonl"))
            bindings = daily._adapter_bindings()
            self.assertEqual(daily.engine._realize_ready_decisions(calendar_fixture._sessions()), 0)
            self.assertEqual(bindings["_realize_ready_decisions"](calendar_fixture._sessions()), 1)
            # A pre-existing batch is not permission to bypass its receipt.
            saved = receipt.with_suffix(".saved")
            receipt.rename(saved)
            with self.assertRaises((ValueError, FileNotFoundError)):
                daily.verify_accepted_final(final)
            with self.assertRaises((ValueError, FileNotFoundError)):
                daily.verified_realized_batch_count()
            saved.rename(receipt)
            self.assertEqual(daily.verified_realized_batch_count(), 1)
            for source, digest in watched.items():
                self.assertEqual(fixture.acceptance.digest(source), digest)
