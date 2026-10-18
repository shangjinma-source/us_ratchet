"""Economic execution E2E: real daily engine; activation boundary isolated.

No scheduler/activation certification is claimed. Network inputs, clock, and
filesystem roots are fixtures; search, receipts, realization and replay are real.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import fixture_fresh_search_v4_e2e as fixture
from backtest import ndx_dynamic_shadow_daily as math_engine
from backtest.ndx_observed_session_calendar_v2 import verify_canonical_reviewed_calendar_v2
from scripts import ndx_dynamic_shadow_daily_v4 as daily


class ExecutionClock(datetime):
    day = 3
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, cls.day, 1, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


class Daily4ExecutionE2ETests(unittest.TestCase):
    def test_real_economic_paths_and_same_day_restart(self):
        self.exercise()

    def exercise(self, *, after_first=None, verify_restart=True):
        """Run real economics; optional adversarial callback runs inside temp bindings."""
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.object(ExecutionClock, "day", 3))
            root = Path(directory).resolve()
            snapshot, watched = fixture.prepare(root)
            calls = []
            fixture.bindings(stack, root, calls)
            accepted = fixture.acceptance.execute(snapshot)
            self.assertEqual(len(calls), 8)
            # Append a real next observed session to the same reviewed calendar.
            helper = fixture.calendar_fixture.NdxObservedSessionCalendarV2Tests()
            paths, _, _ = helper._sources(root / "data/cache", ["2026-09-30", "2026-10-01", "2026-10-02"])
            observed = helper._snapshot(paths, start_date="2026-09-30", observed_at="2026-10-03T01:00:00+00:00")
            fixture.write_canonical_reviewed_calendar_v2(repository_root=root, snapshot=observed,
                calendar_start_date="2026-09-30", prospective_start_date="2026-10-01", initialize_reviewed_v1=False)
            engine = daily.engine
            previous = daily.previous
            for relative in ("scripts/ndx_dynamic_shadow_daily.py", "scripts/ndx_dynamic_shadow_daily_v3.py",
                    "scripts/ndx_dynamic_shadow_daily_v4.py", "backtest/ndx_dynamic_shadow_daily.py",
                    "backtest/ndx_dynamic_shadow_daily_v2.py", "backtest/ndx_dynamic_shadow_daily_v3.py",
                    "config/ndx_dynamic_shadow_daily_v1.yaml", "config/config.yaml"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((fixture.REAL_ROOT / relative).read_bytes())
            for name, value in list(vars(engine).items()):
                if isinstance(value, Path) and value.is_relative_to(fixture.REAL_ROOT):
                    stack.enter_context(patch.object(engine, name, root / value.relative_to(fixture.REAL_ROOT)))
            stack.enter_context(patch.object(engine, "__file__", str(root / "scripts/ndx_dynamic_shadow_daily.py")))
            stack.enter_context(patch.object(engine, "PROTECTED", tuple(root / relative for relative in (
                "config/config.yaml", "data/state.json", "data/broker_positions.json"))))
            # Bind the real OS lock's default argument, not a no-op lock.
            stack.enter_context(patch.object(engine, "single_instance_lock", partial(engine.single_instance_lock, engine.LOCK_PATH)))
            for module, script in ((previous, "scripts/ndx_dynamic_shadow_daily_v3.py"),
                    (daily, "scripts/ndx_dynamic_shadow_daily_v4.py")):
                stack.enter_context(patch.object(module, "ROOT", root))
                stack.enter_context(patch.object(module, "__file__", str(root / script)))
            stack.enter_context(patch.object(previous, "CALENDAR", root / fixture.calendar.CALENDAR_RELATIVE))
            stack.enter_context(patch.object(daily, "GENERATOR_SCRIPT", root / "scripts/ndx_dynamic_shadow_candidate_generator_v3.py"))
            stack.enter_context(patch.object(daily, "_verify_activation", return_value={"isolated_activation_boundary": True}))
            def refresh():
                return verify_canonical_reviewed_calendar_v2(
                    root / fixture.calendar.CALENDAR_RELATIVE, repository_root=root)
            stack.enter_context(patch.object(previous, "_refresh_calendar", side_effect=refresh))
            def command_bridge(command, **kwargs):
                self.assertEqual(command[3], "--verify")
                return fixture.acceptance.candidate.verify(Path(command[4]))
            stack.enter_context(patch.object(previous, "_run_checked", side_effect=command_bridge))
            stack.enter_context(patch.object(engine, "datetime", ExecutionClock))
            stack.enter_context(patch.object(math_engine, "_system_utc_now", side_effect=ExecutionClock.now))
            controls, _, _ = fixture.search.load_frozen_original_8_definition(root / fixture.ORIGINAL)
            tickers = sorted(set(controls) | {"NEW", "O000", "O001", "O002"})
            def nominal(ticker, *, begin, end):
                number = tickers.index(ticker)
                index = pd.bdate_range(end="2026-10-05", periods=302)
                close = 95 + np.arange(302) * .015 + .1 * np.sin(np.arange(302) / (8 + number))
                frame = pd.DataFrame(dict(Open=close, Close=close), index=index)
                return frame.loc[(frame.index >= begin) & (frame.index <= end)], "eastmoney_fqt_0", {}
            stack.enter_context(patch.object(engine, "fetch_unadjusted_bars", side_effect=nominal))
            fixture.write_frame(engine.TARGET_CSV, pd.DataFrame({"Date": ["2026-10-02"], "Close": [1.03]}))
            fixture.write_json(engine.TARGET_MANIFEST, dict(dataset_key="012922", row_count=1,
                content_sha256=fixture.acceptance.digest(engine.TARGET_CSV), publication_time_known=False,
                fetched_at="2026-10-03T00:00:00+00:00"))
            stack.enter_context(patch.object(engine, "get_fund_nav", return_value=(None, SimpleNamespace(cached=False, stale=False))))
            # pandas' clock is used only for runtime observation timestamps here.
            stack.enter_context(patch.object(pd.Timestamp, "now", side_effect=lambda **kwargs: pd.Timestamp(ExecutionClock.now())))
            first = daily.execute()
            self.assertEqual(first["realized_decision_batches"], 1)
            self.assertEqual(first["independent_lane_count"], 10)
            self.assertEqual(first["benchmark_control_count"], 2)
            self.assertEqual(first["appended_lane_path_records"], 10)
            ledgers = list(engine.PATH_ROOT.glob("*.jsonl")) + [engine.ORIGINAL8_LEDGER, engine.TARGET_TRACE_LEDGER]
            before = {path: path.read_bytes() for path in ledgers}
            records = [json.loads(path.read_text().splitlines()[0]) for path in ledgers[:10]]
            self.assertTrue(any(record["trade_events"] for record in records))
            self.assertTrue(any(record["path_state"]["holding_count"] > 0 for record in records))
            if after_first is not None:
                after_first(root, first)
            if not verify_restart:
                for source, digest in watched.items():
                    self.assertEqual(fixture.acceptance.digest(source), digest)
                return
            second = daily.execute()
            self.assertEqual(second["realized_decision_batches"], 1)
            self.assertEqual(second["appended_lane_path_records"], 0)
            self.assertEqual(before, {path: path.read_bytes() for path in ledgers})
            # Advance, never rewrite: existing calendar and economic prefixes survive.
            ExecutionClock.day = 6
            paths, _, _ = helper._sources(root / "data/cache", ["2026-09-30", "2026-10-01", "2026-10-02", "2026-10-05"])
            observed = helper._snapshot(paths, start_date="2026-09-30", observed_at="2026-10-06T01:00:00+00:00")
            fixture.write_canonical_reviewed_calendar_v2(repository_root=root, snapshot=observed,
                calendar_start_date="2026-09-30", prospective_start_date="2026-10-01", initialize_reviewed_v1=False)
            third = daily.execute()
            self.assertEqual(third["latest_observed_session"], "2026-10-05")
            self.assertEqual(third["realized_decision_batches"], 1)
            self.assertEqual(third["appended_lane_path_records"], 10)
            for path in ledgers:
                raw = path.read_bytes()
                self.assertTrue(raw.startswith(before[path]))
                self.assertEqual(len(raw.splitlines()), 2)
                if path != engine.TARGET_TRACE_LEDGER:
                    last = json.loads(raw.splitlines()[-1])
                    self.assertEqual(last["trade_events"], [])
                    self.assertEqual(last["date"], "2026-10-05")
            self.assertEqual(len(calls), 8)
            self.assertEqual(daily.verify_accepted_final(root / fixture.acceptance.SEARCH / "final/2026-10-01/manifest.json"), accepted["receipt"])
            for source, digest in watched.items():
                self.assertEqual(fixture.acceptance.digest(source), digest)
