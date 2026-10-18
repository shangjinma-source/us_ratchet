from __future__ import annotations

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backtest import ndx_dynamic_shadow_daily as v1
from backtest import ndx_dynamic_shadow_daily_v2 as reviewed
from backtest.ndx_observed_session_calendar import (
    load_ohlc_rows,
    prepare_update as prepare_calendar_v1_update,
)
from backtest.ndx_observed_session_calendar_v2 import (
    capture_source_snapshot,
    verify_canonical_reviewed_calendar_v2,
    write_canonical_reviewed_calendar_v2,
)
from data.versioning import file_sha256
from scripts import ndx_dynamic_shadow_daily as daily_engine
from scripts import ndx_dynamic_shadow_daily_v3 as daily_v3


def _sessions(extra: bool = False) -> pd.DataFrame:
    rows = [
        {
            "session_date": "2026-10-01",
            "open_timestamp_utc": "2026-10-01T13:30:00+00:00",
            "close_timestamp_utc": "2026-10-01T20:00:00+00:00",
            "completed": True,
            "is_first_observed_session_of_month": True,
            "next_observed_session_date": "2026-10-02",
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": True,
            "source_price_replay_available": True,
            "session_event_sha256": "1" * 64,
        },
        {
            "session_date": "2026-10-02",
            "open_timestamp_utc": "2026-10-02T13:30:00+00:00",
            "close_timestamp_utc": "2026-10-02T20:00:00+00:00",
            "completed": True,
            "is_first_observed_session_of_month": False,
            "next_observed_session_date": "2026-10-05" if extra else "",
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": False,
            "source_price_replay_available": True,
            "session_event_sha256": "2" * 64,
        },
    ]
    if extra:
        rows.append(
            {
                "session_date": "2026-10-05",
                "open_timestamp_utc": "2026-10-05T13:30:00+00:00",
                "close_timestamp_utc": "2026-10-05T20:00:00+00:00",
                "completed": True,
                "is_first_observed_session_of_month": False,
                "next_observed_session_date": "",
                "origin": "PROSPECTIVE_OBSERVED_APPEND",
                "decision_eligible": False,
                "source_price_replay_available": True,
                "session_event_sha256": "3" * 64,
            }
        )
    return pd.DataFrame(rows)


def _event(sequence: int) -> dict:
    return {"event_sequence": sequence, "event_sha256": str(sequence) * 64}


def _write_lane(path: Path, selector_id: str, date: str = "2026-10-02") -> None:
    record = {
        "schema_version": 1,
        "artifact_type": "ndx_dynamic_shadow_daily_lane_path_record",
        "selector_id": selector_id,
        "date": date,
        "previous_record_sha256": None,
        "path_state": {
            "cash_usd": 100.0,
            "holdings_value_usd": 24900.0,
            "total_value_usd": 25000.0,
            "holding_count": 1,
            "active_security_ids": "security:aaa",
            "active_tickers": "AAA",
            "holdings": "security:aaa:249",
        },
        "rebalance_events": [],
        "trade_events": [],
        "price_evidence_sha256": "a" * 64,
        "independent_lane_only": True,
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    record["record_sha256"] = v1.canonical_sha256(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


def _write_target(path: Path, date: str = "2026-10-02") -> None:
    record = {
        "schema_version": 1,
        "artifact_type": "ndx_dynamic_shadow_target_012922_asof_record",
        "evidence_role": "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME",
        "sequence": 1,
        "session_date": date,
        "status": "TARGET_ASOF_UNAVAILABLE_PENDING",
        "source_date": None,
        "source_close": None,
        "normalized_value_usd": None,
        "lag_calendar_days": None,
        "lag_observed_session_count": None,
        "observed_at_utc": "2026-10-03T01:00:00+00:00",
        "source_csv_snapshot_path": None,
        "source_manifest_snapshot_path": None,
        "source_csv_sha256": None,
        "source_manifest_sha256": None,
        "source_fetched_at_utc": "2026-10-03T00:00:00+00:00",
        "publication_time_known": False,
        "previous_record_sha256": None,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    record["record_sha256"] = v1.canonical_sha256(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


class DynamicShadowDailyV2Tests(unittest.TestCase):
    def _fixture(self, root: Path):
        calendar = root / reviewed.CALENDAR_RELATIVE
        ledger = calendar.parent / "events.jsonl"
        calendar.parent.mkdir(parents=True)
        calendar.write_text("{}\n", encoding="utf-8")
        events = [_event(1), _event(2)]
        ledger.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
            encoding="utf-8",
        )
        projection = _sessions()
        verified = SimpleNamespace(events=tuple(events), session_projection=tuple())
        calendar_manifest = {"artifacts": {"event_ledger": {"path": ledger.as_posix()}}}
        daily_root = root / "data/cache/research/ndx_dynamic_shadow_daily_v1"
        lanes = {}
        for selector_id in reviewed._selector_ids():
            path = daily_root / "lane_paths" / f"{selector_id}.jsonl"
            _write_lane(path, selector_id)
            lanes[selector_id] = path
        original = daily_root / "benchmark_controls/original_8_incumbent_v0.jsonl"
        _write_lane(original, "ndx_original_8_incumbent_v0")
        target = daily_root / "benchmark_controls/target_012922_asof.jsonl"
        _write_target(target)
        output = daily_root / "three_way_calendar_alignment/2026-10-02"
        return calendar, ledger, calendar_manifest, verified, projection, lanes, original, target, output

    def test_alignment_uses_sealed_dates_and_timestamps_and_all_twelve_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self._fixture(root)
            calendar, _, payload, verified, sessions, lanes, original, target, output = values
            with patch.object(
                reviewed, "load_reviewed_calendar_projection",
                return_value=(payload, verified, v1.normalize_observed_sessions(sessions)),
            ):
                manifest = reviewed.write_three_way_calendar_manifest(
                    output,
                    selector_lane_ledgers=lanes,
                    original_8_ledger=original,
                    target_012922_ledger=target,
                    observed_sessions=sessions,
                    observed_calendar_manifest_path=calendar,
                )
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(len(manifest["selector_lane_prefixes"]), 10)
            self.assertEqual(manifest["benchmark_control_count"], 2)
            frozen = pd.read_csv(output / "calendar_sessions.csv")
            self.assertEqual(frozen["session_date"].astype(str).tolist(), ["2026-10-02"])
            self.assertEqual(frozen.iloc[0]["open_timestamp_utc"], "2026-10-02T13:30:00+00:00")
            self.assertFalse(manifest["observed_calendar_source"]["current_vendor_data_used"])

    def test_caller_sessions_cannot_override_sealed_open_or_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self._fixture(root)
            calendar, _, payload, verified, sessions, lanes, original, target, output = values
            supplied = sessions.copy()
            supplied.loc[1, "open_timestamp_utc"] = "2026-10-02T14:30:00+00:00"
            with patch.object(
                reviewed, "load_reviewed_calendar_projection",
                return_value=(payload, verified, v1.normalize_observed_sessions(sessions)),
            ), self.assertRaisesRegex(reviewed.NdxDynamicShadowDailyV2Error, "caller observed"):
                reviewed.write_three_way_calendar_manifest(
                    output, selector_lane_ledgers=lanes,
                    original_8_ledger=original, target_012922_ledger=target,
                    observed_sessions=supplied, observed_calendar_manifest_path=calendar,
                )

    def test_event_ledger_may_append_but_cannot_rewrite_frozen_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self._fixture(root)
            calendar, ledger, payload, verified, sessions, lanes, original, target, output = values
            with patch.object(
                reviewed, "load_reviewed_calendar_projection",
                return_value=(payload, verified, v1.normalize_observed_sessions(sessions)),
            ):
                reviewed.write_three_way_calendar_manifest(
                    output, selector_lane_ledgers=lanes,
                    original_8_ledger=original, target_012922_ledger=target,
                    observed_sessions=sessions, observed_calendar_manifest_path=calendar,
                )
            appended_events = [*verified.events, _event(3)]
            ledger.write_text(
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in appended_events),
                encoding="utf-8",
            )
            extended = SimpleNamespace(events=tuple(appended_events), session_projection=tuple())
            with patch.object(
                reviewed, "load_reviewed_calendar_projection",
                return_value=(payload, extended, v1.normalize_observed_sessions(_sessions(extra=True))),
            ):
                reviewed.verify_three_way_calendar_manifest(output / "manifest.json")
            lines = ledger.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])
            first["event_sha256"] = "9" * 64
            lines[0] = json.dumps(first, sort_keys=True)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with patch.object(
                reviewed, "load_reviewed_calendar_projection",
                return_value=(payload, extended, v1.normalize_observed_sessions(_sessions(extra=True))),
            ), self.assertRaisesRegex(reviewed.NdxDynamicShadowDailyV2Error, "prefix was rewritten"):
                reviewed.verify_three_way_calendar_manifest(output / "manifest.json")

    def test_daily_run_verifier_requires_v2_runtime_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calendar = root / reviewed.CALENDAR_RELATIVE
            paths = {
                "daily_contract": root / "config/ndx_dynamic_shadow_daily_v1.yaml",
                "daily_engine": root / "backtest/ndx_dynamic_shadow_daily_v2.py",
                "daily_script": root / "scripts/ndx_dynamic_shadow_daily_v3.py",
                "observed_calendar_manifest": calendar,
            }
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                if path == paths["daily_contract"]:
                    shutil.copyfile(
                        Path(__file__).resolve().parents[1]
                        / "config/ndx_dynamic_shadow_daily_v1.yaml",
                        path,
                    )
                else:
                    path.write_text(path.name + "\n", encoding="utf-8")
            artifacts = {
                key: {"path": path.resolve().as_posix(), "sha256": file_sha256(path)}
                for key, path in paths.items()
            }
            artifacts.update({
                "realized_batch_manifests": {}, "selector_lane_ledgers": {},
                "original_8_control_ledger": None, "target_012922_trace_ledger": None,
                "three_way_alignment_manifest": None, "nominal_price_evidence_manifest": None,
            })
            run = {
                "schema_version": 1,
                "manifest_type": "ndx_dynamic_shadow_daily_run",
                "generated_at": "2026-10-03T01:00:00+00:00",
                "status": "RESEARCH_DAILY_COMPLETE",
                "calendar_manifest_sha256": artifacts["observed_calendar_manifest"]["sha256"],
                "latest_observed_session": "2026-10-02",
                "decision_phases": {},
                "realized_decision_batches": 0,
                "independent_lane_count": 0,
                "benchmark_control_count": 0,
                "appended_lane_path_records": 0,
                "original_8_control_rows": 0,
                "target_012922_trace_rows": 0,
                "target_012922_pending_rows": 0,
                "target_012922_source_error": None,
                "three_way_alignment_manifest": None,
                "research_artifacts": artifacts,
                "single_instance_lock_used": True,
                "historical_candidate_replay_used": False,
                "retrospective_decision_backfill_used": False,
                "automation_registered": False,
                "promotion_allowed": False,
                "live_mutation": False,
            }
            run["run_manifest_sha256"] = v1.canonical_sha256(run)
            run_path = root / "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json"
            run_path.parent.mkdir(parents=True)
            run_path.write_text(json.dumps(run), encoding="utf-8")
            projection = v1.normalize_observed_sessions(_sessions())
            with patch.object(
                reviewed, "load_reviewed_calendar_projection",
                return_value=({}, SimpleNamespace(events=()), projection),
            ):
                reviewed.verify_daily_run_manifest(run_path, repository_root=root)

            old_engine = root / "backtest/ndx_dynamic_shadow_daily.py"
            old_engine.write_text("old\n", encoding="utf-8")
            run["research_artifacts"]["daily_engine"] = {
                "path": old_engine.resolve().as_posix(), "sha256": file_sha256(old_engine),
            }
            unsigned = dict(run)
            unsigned.pop("run_manifest_sha256")
            run["run_manifest_sha256"] = v1.canonical_sha256(unsigned)
            run_path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaisesRegex(reviewed.NdxDynamicShadowDailyV2Error, "runtime provenance"):
                reviewed.verify_daily_run_manifest(run_path, repository_root=root)

    def test_full_daily_v3_pre_october_run_uses_real_reviewed_calendar_and_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "backtest/ndx_observed_session_calendar_v2.py",
                "scripts/ndx_observed_session_calendar_v2.py",
                "backtest/ndx_dynamic_shadow_daily_v2.py",
                "scripts/ndx_dynamic_shadow_daily_v3.py",
                "config/ndx_dynamic_shadow_daily_v1.yaml",
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(__file__).resolve().parents[1] / relative, destination)
            protected = (
                root / "config/config.yaml",
                root / "data/state.json",
                root / "data/broker_positions.json",
            )
            for index, path in enumerate(protected):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"protected-{index}\n", encoding="utf-8")
            protected_before = {path: file_sha256(path) for path in protected}

            source_paths: dict[str, Path] = {}
            source_rows = {}
            source_hashes = {}
            for offset, ticker in enumerate(("QQQ", "SPY")):
                path = root / f"data/cache/{ticker}.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                base = 100 + offset * 10
                path.write_text(
                    "Date,Open,High,Low,Close,Volume\n"
                    f"2026-09-30,{base},{base + 2},{base - 2},{base + 1},1000000\n",
                    encoding="utf-8",
                )
                source_paths[ticker] = path
                source_rows[ticker] = load_ohlc_rows(path, ticker=ticker)
                source_hashes[ticker] = file_sha256(path)
            legacy_records = prepare_calendar_v1_update(
                [], completed_dates=["2026-09-30"], tickers=["QQQ", "SPY"],
                source_rows=source_rows, source_snapshot_sha256=source_hashes,
                prospective_start_date="2026-10-01",
                recorded_at_utc=pd.Timestamp("2026-10-01T01:00:00Z").to_pydatetime(),
                bootstrap=True,
            )
            legacy_root = root / "data/cache/research/ndx_observed_us_session_calendar_v1"
            legacy_root.mkdir(parents=True)
            legacy_ledger = legacy_root / "sessions.jsonl"
            legacy_ledger.write_text(
                "".join(json.dumps(record, sort_keys=True) + "\n" for record in legacy_records),
                encoding="utf-8",
            )
            legacy_manifest = legacy_root / "manifest.json"
            legacy_manifest.write_text(json.dumps({
                "manifest_type": "ndx_observed_us_session_calendar",
                "prospective_start_date": "2026-10-01",
                "artifacts": {"append_only_ledger": {
                    "path": legacy_ledger.resolve().as_posix(),
                    "sha256": file_sha256(legacy_ledger),
                    "rows": len(legacy_records),
                }},
            }), encoding="utf-8")
            snapshot = capture_source_snapshot(
                source_paths, tickers=["QQQ", "SPY"], start_date="2026-09-30",
                observed_at_utc=pd.Timestamp("2026-10-01T02:00:00Z").to_pydatetime(),
            )
            written = write_canonical_reviewed_calendar_v2(
                repository_root=root, snapshot=snapshot,
                calendar_start_date="2026-09-30",
                prospective_start_date="2026-10-01",
                initialize_reviewed_v1=True,
            )
            calendar = written.manifest_path
            verify_canonical_reviewed_calendar_v2(calendar, repository_root=root)

            orchestrator = root / "data/cache/research/ndx_dynamic_shadow_daily_v1"
            controls = orchestrator / "benchmark_controls"
            path_values = {
                "ROOT": root,
                "CONTRACT": root / "config/ndx_dynamic_shadow_daily_v1.yaml",
                "CALENDAR_MANIFEST": calendar,
                "INPUT_ROOT": root / "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1",
                "SEARCH_ROOT": root / "data/cache/research/ndx_dynamic_shadow_fresh_search_v1",
                "ORCHESTRATOR_ROOT": orchestrator,
                "REALIZED_ROOT": orchestrator / "realized_decisions",
                "PATH_ROOT": orchestrator / "lane_paths",
                "PRICE_ROOT": orchestrator / "nominal_price_evidence",
                "CONTROL_ROOT": controls,
                "ORIGINAL8_LEDGER": controls / "original_8_incumbent_v0.jsonl",
                "TARGET_TRACE_LEDGER": controls / "target_012922_asof.jsonl",
                "TARGET_SOURCE_ROOT": controls / "target_012922_sources",
                "ALIGNMENT_ROOT": orchestrator / "three_way_calendar_alignment",
                "ORIGINAL8_MANIFEST": root / "data/cache/research/ndx_original_8_control_v1/manifest.json",
                "TARGET_CSV": root / "data/cache/funds/012922.csv",
                "TARGET_MANIFEST": root / "data/cache/funds/012922.csv.manifest.json",
                "DISPOSITION_LEDGER": orchestrator / "decision_dispositions.jsonl",
                "LOCK_PATH": orchestrator / ".daily.lock",
                "PROTECTED": protected,
            }
            original_lock = daily_engine.single_instance_lock

            def temp_lock():
                return original_lock(path_values["LOCK_PATH"])

            def verified_refresh():
                verify_canonical_reviewed_calendar_v2(calendar, repository_root=root)

            with patch.multiple(daily_engine, **path_values), patch.object(
                daily_engine, "single_instance_lock", temp_lock,
            ), patch.multiple(
                daily_v3,
                ROOT=root,
                CALENDAR=calendar,
                __file__=str(root / "scripts/ndx_dynamic_shadow_daily_v3.py"),
            ), patch.object(
                daily_v3, "_verify_activation", return_value={"verified": True},
            ), patch.object(daily_v3, "_refresh_calendar", side_effect=verified_refresh):
                result = daily_v3.execute()

            latest = orchestrator / "latest_run.json"
            self.assertEqual(result["latest_observed_session"], "2026-09-30")
            self.assertEqual(result["decision_phases"], [])
            self.assertEqual(result["independent_lane_count"], 0)
            self.assertEqual(
                reviewed.verify_daily_run_manifest(latest, repository_root=root)["status"],
                "RESEARCH_DAILY_COMPLETE",
            )
            self.assertEqual(
                protected_before, {path: file_sha256(path) for path in protected},
            )


if __name__ == "__main__":
    unittest.main()
