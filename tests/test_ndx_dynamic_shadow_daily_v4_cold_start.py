"""Cold daily4 execution: source fixtures only, real candidate seal and search."""
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import partial
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import fixture_daily_v4_cold_start as raw
import fixture_fresh_search_v4_e2e as fixture
from backtest.ndx_observed_session_calendar_v2 import verify_canonical_reviewed_calendar_v2
from backtest import ndx_dynamic_shadow_daily as math_engine
from backtest.ndx_dynamic_shadow_daily_economic_replay import verify_daily_economic_replay
from scripts import ndx_dynamic_shadow_daily_v4 as daily


class ColdClock(datetime):
    day = 2
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, cls.day, 1, 15, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


class Daily4ColdStartTests(unittest.TestCase):
    def test_missing_snapshot_sealed_by_real_generator_and_searched(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.object(ColdClock, "day", 2))
            root = Path(directory).resolve()
            calendar_helper = fixture.calendar_fixture.NdxObservedSessionCalendarV2Tests()
            calendar_sources = calendar_helper._canonical_repository(root, ["2026-09-30", "2026-10-01"])
            sources, evidence, watched = raw.prepare_raw_sources(root)
            taxonomy = raw.run_taxonomy(root, evidence)
            self.assertEqual(taxonomy["summary"]["classified_security_count"], 4)
            for relative in (str(fixture.calendar.ENGINE_RELATIVE), str(fixture.calendar.CALENDAR_SCRIPT_RELATIVE),
                    str(fixture.calendar.ADAPTER_RELATIVE), "scripts/ndx_dynamic_shadow_daily.py",
                    "scripts/ndx_dynamic_shadow_daily_v3.py", "scripts/ndx_dynamic_shadow_daily_v4.py",
                    "backtest/ndx_dynamic_shadow_daily.py", "backtest/ndx_dynamic_shadow_daily_v2.py",
                    "backtest/ndx_dynamic_shadow_daily_v3.py", "config/ndx_dynamic_shadow_daily_v1.yaml"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((fixture.REAL_ROOT / relative).read_bytes())
            snapshot = calendar_helper._snapshot(calendar_sources, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00")
            fixture.write_canonical_reviewed_calendar_v2(repository_root=root, snapshot=snapshot,
                calendar_start_date="2026-09-30", prospective_start_date="2026-10-01", initialize_reviewed_v1=True)
            calls = []
            fixture.bindings(stack, root, calls)
            candidate = fixture.acceptance.candidate
            generator = fixture.generator
            engine = daily.engine
            for module in (engine, daily, daily.previous, generator, candidate):
                for name, value in list(vars(module).items()):
                    if isinstance(value, Path) and value.is_relative_to(fixture.REAL_ROOT):
                        stack.enter_context(patch.object(module, name, root / value.relative_to(fixture.REAL_ROOT)))
            for module, filename in ((engine, "scripts/ndx_dynamic_shadow_daily.py"),
                    (daily, "scripts/ndx_dynamic_shadow_daily_v4.py"),
                    (daily.previous, "scripts/ndx_dynamic_shadow_daily_v3.py"),
                    (generator, "scripts/ndx_dynamic_shadow_candidate_generator.py")):
                stack.enter_context(patch.object(module, "__file__", str(root / filename)))
            stack.enter_context(patch.object(generator, "CANONICAL_ARGUMENT_PATHS", {
                name: root / path.relative_to(fixture.REAL_ROOT) for name, path in generator.CANONICAL_ARGUMENT_PATHS.items()}))
            defaults = dict(generator._append_decision_seal.__kwdefaults__)
            defaults["expected_root"] = root / fixture.acceptance.INPUT
            stack.enter_context(patch.object(generator._append_decision_seal, "__kwdefaults__", defaults))
            protected = tuple(root / rel for rel in ("config/config.yaml", "data/state.json", "data/broker_positions.json"))
            for module in (generator, engine):
                stack.enter_context(patch.object(module, "PROTECTED", protected))
                stack.enter_context(patch.object(module, "datetime", ColdClock))
            for module in (fixture.leaf, fixture.controller, fixture.search):
                stack.enter_context(patch.object(module, "datetime", ColdClock))
            stack.enter_context(patch.object(pd.Timestamp, "now", side_effect=lambda **kwargs: pd.Timestamp(ColdClock.now())))
            stack.enter_context(patch.object(math_engine, "_system_utc_now", side_effect=ColdClock.now))
            stack.enter_context(patch.object(engine, "single_instance_lock", partial(engine.single_instance_lock, engine.LOCK_PATH)))
            stack.enter_context(patch.object(daily, "_verify_activation", return_value={"activation_boundary_isolated": True}))
            stack.enter_context(patch.object(daily.previous, "_refresh_calendar", side_effect=lambda: verify_canonical_reviewed_calendar_v2(
                root / fixture.calendar.CALENDAR_RELATIVE, repository_root=root)))
            official = pd.read_csv(sources["official_snapshot_sha256"])
            official_manifest = json.loads(sources["official_snapshot_manifest_sha256"].read_bytes())
            official_manifest.update(archive_path=str(sources["official_snapshot_sha256"]), fetched_at="2026-10-01T20:05:00+00:00")
            stack.enter_context(patch.object(generator, "get_nasdaq_100_snapshot", return_value=(official,
                SimpleNamespace(cached=False, stale=False, manifest=official_manifest))))
            history = pd.read_csv(sources["membership_history_sha256"], dtype=str)
            stack.enter_context(patch.object(generator, "get_ndx_point_in_time_history", return_value=(history, SimpleNamespace(cached=False, stale=False))))
            controls, _, _ = fixture.search.load_frozen_original_8_definition(root / fixture.ORIGINAL)
            tickers = sorted(set(controls) | {"NEW", "O000", "O001", "O002"})
            def bars(ticker):
                number = tickers.index(ticker)
                index = pd.bdate_range(end="2026-10-02", periods=301)
                close = 95 + np.arange(301) * .015 + .1 * np.sin(np.arange(301) / (8 + number))
                return pd.DataFrame(dict(Open=close, High=close + 1, Low=close - 1, Close=close,
                    Volume=2_000_000.0), index=pd.DatetimeIndex(index, name="Date"))
            def adjusted(ticker, cfg):
                frame = bars(ticker).loc[:"2026-10-01"]
                fixture.write_frame(Path(cfg.cache_dir) / f"{ticker}.csv", frame.reset_index())
                return frame, SimpleNamespace(cached=False)
            stack.enter_context(patch.object(generator, "get_bars", side_effect=adjusted))
            def nominal(ticker, *, begin, end):
                frame = bars(ticker)
                return frame.loc[(frame.index >= begin) & (frame.index <= end)], "eastmoney_fqt_0", {}
            stack.enter_context(patch.object(generator, "fetch_unadjusted_bars", side_effect=nominal))
            stack.enter_context(patch.object(engine, "fetch_unadjusted_bars", side_effect=nominal))
            def fund(*args, **kwargs):
                dates = pd.bdate_range(end="2026-10-01", periods=300)
                frame = pd.DataFrame(dict(Date=dates, Close=1 + np.arange(300) * .0001))
                path = root / "data/cache/funds/012922.csv"
                fixture.write_frame(path, frame)
                fixture.write_json(path.with_suffix(".csv.manifest.json"), dict(dataset_key="012922",
                    content_sha256=fixture.acceptance.digest(path), row_count=len(frame), publication_time_known=False,
                    fetched_at="2026-10-01T20:05:00+00:00"))
                return frame, SimpleNamespace(cached=False, stale=False)
            stack.enter_context(patch.object(generator, "get_fund_nav", side_effect=fund))
            stack.enter_context(patch.object(engine, "get_fund_nav", side_effect=fund))
            rebuild_calls = []
            def taxonomy_bridge(command, **kwargs):
                self.assertEqual(command[:2], [sys.executable, "-B"])
                self.assertEqual(Path(command[2]), root / "scripts/ndx_taxonomy_v2.py")
                self.assertEqual(command[3:], ["--plan-only", "--evidence-csv", str(evidence)])
                rebuild_calls.append(command)
                raw.run_taxonomy(root, evidence)
                return SimpleNamespace(returncode=0, stdout="real taxonomy rebuilt", stderr="")
            stack.enter_context(patch.object(generator, "subprocess", SimpleNamespace(run=taxonomy_bridge)))
            stages = []
            def bridge(command, **kwargs):
                self.assertEqual(command[:2], [sys.executable, "-B"])
                script = Path(command[2])
                stages.append(script.name)
                if script.name == "ndx_dynamic_shadow_candidate_generator_v3.py":
                    args = candidate.parse_args(command[3:])
                    if args.seal:
                        self.assertFalse((root / fixture.acceptance.INPUT / "2026-10-01/manifest.json").exists())
                        return candidate.seal(args)
                    return candidate.verify(args.verify)
                self.assertEqual(script.name, "ndx_dynamic_shadow_fresh_search_v4.py")
                self.assertEqual(command[3:5], ["--execute", "--snapshot-manifest"])
                self.assertEqual(len(command), 6)
                self.assertEqual(Path(command[5]), root / fixture.acceptance.INPUT / "2026-10-01/manifest.json")
                return fixture.acceptance.execute(Path(command[-1]))
            stack.enter_context(patch.object(daily.previous, "_run_checked", side_effect=bridge))
            self.assertFalse((root / fixture.acceptance.INPUT).exists())
            self.assertFalse((root / fixture.acceptance.SEARCH).exists())
            self.assertFalse((root / fixture.acceptance.ACCEPTANCE).exists())
            result = daily.execute()
            self.assertEqual(len(calls), 8, result)
            self.assertEqual(len(rebuild_calls), 1)
            self.assertIn("ndx_dynamic_shadow_fresh_search_v4.py", stages)
            self.assertEqual(result["independent_lane_count"], 0)
            self.assertEqual(result["decision_phases"][0]["phase"], "WAIT_FOR_NEXT_OBSERVED_SESSION")
            receipt = fixture.acceptance.verify_acceptance(root / fixture.acceptance.ACCEPTANCE / "2026-10-01/receipt.json")
            self.assertEqual(receipt["decision_date"], "2026-10-01")
            seals = [root / fixture.acceptance.INPUT / "2026-10-01/manifest.json",
                     root / fixture.acceptance.INPUT / "decision_seals.jsonl",
                     root / fixture.acceptance.SEARCH / "final/2026-10-01/manifest.json",
                     root / fixture.acceptance.SEARCH / "role_seals.jsonl",
                     root / fixture.acceptance.ACCEPTANCE / "2026-10-01/receipt.json"]
            sealed_bytes = {path: path.read_bytes() for path in seals}
            ColdClock.day = 3
            calendar_sources, _, _ = calendar_helper._sources(root / "data/cache", ["2026-09-30", "2026-10-01", "2026-10-02"])
            observed = calendar_helper._snapshot(calendar_sources, start_date="2026-09-30", observed_at="2026-10-03T01:00:00+00:00")
            fixture.write_canonical_reviewed_calendar_v2(repository_root=root, snapshot=observed,
                calendar_start_date="2026-09-30", prospective_start_date="2026-10-01", initialize_reviewed_v1=False)
            realized = daily.execute()
            self.assertEqual(realized["realized_decision_batches"], 1)
            self.assertEqual(realized["independent_lane_count"], 10)
            self.assertEqual(realized["benchmark_control_count"], 2)
            self.assertEqual(realized["appended_lane_path_records"], 10)
            self.assertEqual(len(calls), 8)
            self.assertEqual(len(rebuild_calls), 1)
            self.assertEqual(sealed_bytes, {path: path.read_bytes() for path in seals})
            rows = [json.loads(path.read_text().splitlines()[0]) for path in engine.PATH_ROOT.glob("*.jsonl")]
            self.assertTrue(any(row["trade_events"] for row in rows))
            self.assertTrue(any(row["path_state"]["holding_count"] > 0 for row in rows))
            economic = verify_daily_economic_replay(realized, repository_root=root)
            self.assertEqual(economic["economic_lane_count"], 11)
            self.assertEqual(economic["verified_rows"], 11)
            for source, digest in watched.items():
                self.assertEqual(fixture.acceptance.digest(source), digest)
