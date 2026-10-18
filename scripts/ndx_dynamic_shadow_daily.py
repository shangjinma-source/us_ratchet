r"""Run the research-only prospective dynamic-shadow state machine.

Readiness (safe today):
    python -B scripts\ndx_dynamic_shadow_daily.py --readiness

Manual research orchestration after the first eligible October decision close:
    python -B scripts\ndx_dynamic_shadow_daily.py --execute

This entry point never registers a task and never writes live config, broker
state, today's advice, or orders.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_activation_readiness import (  # noqa: E402
    verify_observed_session_calendar_manifest,
)
from backtest.ndx_dynamic_shadow_daily import (  # noqa: E402
    NdxDynamicShadowDailyError,
    append_lane_path,
    append_target_012922_trace,
    build_daily_readiness,
    build_realized_lane_decisions,
    canonical_sha256,
    classify_daily_phase,
    decision_coordinates,
    load_lane_path_ledger,
    load_target_012922_trace_ledger,
    normalize_observed_sessions,
    replay_lane_path,
    replay_original8_control_path,
    validate_nominal_price_evidence,
    verify_daily_run_manifest,
    verify_realized_decision_batch,
    verify_realized_decision_chain,
    verify_three_way_calendar_manifest,
    write_immutable_realized_decisions,
    write_three_way_calendar_manifest,
)
from backtest.ndx_dynamic_shadow_fresh_search import (  # noqa: E402
    load_frozen_original_8_definition,
    verify_final_role_seal_record,
    verify_final_candidate_snapshot,
)
from core.config import load_config  # noqa: E402
from data.fetch import get_bars  # noqa: E402
from data.funds import get_fund_nav  # noqa: E402
from data.ndx_price_basis import fetch_unadjusted_bars  # noqa: E402
from data.versioning import file_sha256  # noqa: E402


CONTRACT = ROOT / "config/ndx_dynamic_shadow_daily_v1.yaml"
CALENDAR_MANIFEST = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
INPUT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1"
SEARCH_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_fresh_search_v1"
ORCHESTRATOR_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_daily_v1"
ACTIVATION_V2_MANIFEST = (
    ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
)
REALIZED_ROOT = ORCHESTRATOR_ROOT / "realized_decisions"
PATH_ROOT = ORCHESTRATOR_ROOT / "lane_paths"
PRICE_ROOT = ORCHESTRATOR_ROOT / "nominal_price_evidence"
CONTROL_ROOT = ORCHESTRATOR_ROOT / "benchmark_controls"
ORIGINAL8_LEDGER = CONTROL_ROOT / "original_8_incumbent_v0.jsonl"
TARGET_TRACE_LEDGER = CONTROL_ROOT / "target_012922_asof.jsonl"
TARGET_SOURCE_ROOT = CONTROL_ROOT / "target_012922_sources"
ALIGNMENT_ROOT = ORCHESTRATOR_ROOT / "three_way_calendar_alignment"
ORIGINAL8_MANIFEST = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"
TARGET_CSV = ROOT / "data/cache/funds/012922.csv"
TARGET_MANIFEST = ROOT / "data/cache/funds/012922.csv.manifest.json"
DISPOSITION_LEDGER = ORCHESTRATOR_ROOT / "decision_dispositions.jsonl"
LOCK_PATH = ORCHESTRATOR_ROOT / ".daily.lock"
PROTECTED = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)


def _protected_hashes() -> dict[str, str | None]:
    return {
        path.relative_to(ROOT).as_posix(): file_sha256(path) if path.is_file() else None
        for path in PROTECTED
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


@contextmanager
def single_instance_lock(path: Path = LOCK_PATH):
    """Hold an OS-released nonblocking lock; crashes do not leave a stale lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise NdxDynamicShadowDailyError("another daily orchestrator instance is running") from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise NdxDynamicShadowDailyError("another daily orchestrator instance is running") from exc
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _run_checked(command: list[str], *, timeout_seconds: float | None = None) -> None:
    try:
        completed = subprocess.run(
            command, cwd=ROOT, check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise NdxDynamicShadowDailyError("fresh search exceeded the pre-open seal deadline") from exc
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout or "").splitlines()[-20:])
        raise NdxDynamicShadowDailyError(
            f"research stage failed rc={completed.returncode}: {command[2] if len(command) > 2 else command[0]}\n{tail}"
        )


def _calendar_sessions() -> tuple[dict[str, Any], pd.DataFrame]:
    audit = verify_observed_session_calendar_manifest(CALENDAR_MANIFEST, ROOT)
    if not audit.get("verified"):
        raise NdxDynamicShadowDailyError("canonical observed-session calendar is not verified")
    manifest = json.loads(CALENDAR_MANIFEST.read_text(encoding="utf-8"))
    item = (manifest.get("artifacts") or {}).get("session_projection") or {}
    path = Path(str(item.get("path") or "")).resolve()
    if (
        path != (CALENDAR_MANIFEST.parent / "sessions.csv").resolve()
        or not path.is_file()
        or file_sha256(path) != item.get("sha256")
    ):
        raise NdxDynamicShadowDailyError("observed-session projection binding changed")
    return manifest, normalize_observed_sessions(pd.read_csv(path, low_memory=False))


def _refresh_calendar() -> None:
    cfg = load_config(ROOT / "config/config.yaml")
    for ticker in ("QQQ", "SPY"):
        get_bars(ticker, cfg)
    _run_checked([
        sys.executable, "-B", str(ROOT / "scripts/ndx_observed_session_calendar.py"), "--execute"
    ])


def _input_manifest(decision_date: str) -> Path:
    return INPUT_ROOT / decision_date / "manifest.json"


def _final_manifest(decision_date: str) -> Path:
    return SEARCH_ROOT / "final" / decision_date / "manifest.json"


def _decision_paths(decision_date: str) -> list[Path]:
    directory = REALIZED_ROOT / decision_date
    return sorted(
        path for path in directory.glob("*.json") if path.name != "batch_manifest.json"
    ) if directory.is_dir() else []


def candidate_generator_command(decision_date: str) -> list[str]:
    return [
        sys.executable, "-B", str(ROOT / "scripts/ndx_dynamic_shadow_candidate_generator.py"),
        "--seal", "--decision-date", decision_date,
        "--session-calendar-manifest", str(CALENDAR_MANIFEST),
        "--refresh-official", "--refresh-membership", "--rebuild-taxonomy",
        "--refresh-prices", "--refresh-nominal-prices", "--refresh-target",
        "--allow-degraded-reviewed-taxonomy-subset",
    ]


def fresh_search_command(decision_date: str, *, max_jobs: int = 0) -> list[str]:
    command = [
        sys.executable, "-B", str(ROOT / "scripts/ndx_dynamic_shadow_fresh_search.py"),
        "--execute", "--resume", "--snapshot-manifest", str(_input_manifest(decision_date)),
    ]
    if int(max_jobs) > 0:
        command.extend(["--max-jobs", str(int(max_jobs))])
    return command


def _verify_input_seal(decision_date: str) -> None:
    _run_checked([
        sys.executable, "-B", str(ROOT / "scripts/ndx_dynamic_shadow_candidate_generator.py"),
        "--verify", str(_input_manifest(decision_date)),
    ])


def _load_dispositions() -> list[dict[str, Any]]:
    if not DISPOSITION_LEDGER.exists():
        return []
    rows = []
    previous = None
    for line in DISPOSITION_LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise NdxDynamicShadowDailyError("blank disposition ledger row")
        row = json.loads(line)
        declared = row.get("record_sha256")
        unsigned = dict(row)
        unsigned.pop("record_sha256", None)
        if canonical_sha256(unsigned) != declared or row.get("previous_record_sha256") != previous:
            raise NdxDynamicShadowDailyError("disposition ledger hash chain changed")
        rows.append(row)
        previous = declared
    dates = [row["decision_date"] for row in rows]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise NdxDynamicShadowDailyError("disposition coordinates changed")
    return rows


def _append_no_decision(decision_date: str, reason: str) -> dict[str, Any]:
    rows = _load_dispositions()
    existing = [row for row in rows if row["decision_date"] == decision_date]
    if existing:
        return existing[0]
    row = {
        "schema_version": 1,
        "artifact_type": "ndx_dynamic_shadow_decision_disposition",
        "decision_date": decision_date,
        "status": "NO_DECISION_NO_BACKFILL",
        "reason": reason,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_record_sha256": rows[-1]["record_sha256"] if rows else None,
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    row["record_sha256"] = canonical_sha256(row)
    DISPOSITION_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with DISPOSITION_LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    _load_dispositions()
    return row


def _load_previous_heads(before_date: str) -> dict[str, dict[str, Any]]:
    lanes = _all_lane_decisions(before_date=before_date)
    return {selector_id: values[-1] for selector_id, values in lanes.items()}


def _all_lane_decisions(*, before_date: str | None = None) -> dict[str, list[dict[str, Any]]]:
    lanes: dict[str, list[dict[str, Any]]] = {}
    if not REALIZED_ROOT.is_dir():
        return lanes
    verify_realized_decision_chain(REALIZED_ROOT)
    for directory in sorted(path for path in REALIZED_ROOT.iterdir() if path.is_dir()):
        if directory.name.startswith(".") or (before_date is not None and directory.name >= before_date):
            continue
        verify_realized_decision_batch(directory)
        files = sorted(path for path in directory.glob("*.json") if path.name != "batch_manifest.json")
        if len(files) != 10:
            raise NdxDynamicShadowDailyError("realized decision directory is not a 10-lane matrix")
        for path in files:
            item = json.loads(path.read_text(encoding="utf-8"))
            declared = item.get("payload_sha256")
            unsigned = dict(item)
            unsigned.pop("payload_sha256", None)
            if canonical_sha256(unsigned) != declared:
                raise NdxDynamicShadowDailyError("realized decision artifact hash changed")
            lanes.setdefault(item["selector_id"], []).append(item)
    expected = {
        f"{track}__{role.lower()}__v1"
        for track in ("strict_technology", "technology_plus_adjacent")
        for role in ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
    }
    if lanes and set(lanes) != expected:
        raise NdxDynamicShadowDailyError("realized decisions do not contain the exact 10 lanes")
    for selector_id, values in lanes.items():
        previous = None
        previous_date = None
        for sequence, item in enumerate(values, start=1):
            decision_date = str((item.get("timing") or {}).get("decision_date") or "")
            if (
                int(item.get("decision_sequence", -1)) != sequence
                or item.get("previous_decision_sha256") != previous
                or previous_date is not None and decision_date <= previous_date
            ):
                raise NdxDynamicShadowDailyError("realized lane decision prefix changed")
            previous = str(item["payload_sha256"])
            previous_date = decision_date
    return lanes


def _selected_tickers(lanes: Mapping[str, Iterable[Mapping[str, Any]]]) -> list[str]:
    values = set()
    for decisions in lanes.values():
        for decision in decisions:
            candidate = decision.get("selected_candidate") or {}
            for target in (candidate.get("targets") or {}).values():
                values.add(str(target["ticker"]).upper())
    return sorted(values)


def _nominal_price_evidence(
    tickers: list[str], sessions: pd.DataFrame, *, valuation_end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    if not tickers:
        empty = pd.DataFrame(index=pd.to_datetime(sessions["session_date"]))
        return empty, empty, {str(value.date()): "0" * 64 for value in empty.index}
    end = pd.Timestamp(valuation_end_date).normalize()
    directory = PRICE_ROOT / end.date().isoformat()
    data_path = directory / "prices.csv"
    manifest_path = directory / "manifest.json"
    expected_manifest_keys = {
        "schema_version", "manifest_type", "status", "valuation_end_date",
        "tickers", "price_basis", "execution_field", "valuation_field",
        "sources", "artifact", "module_sha256", "script_sha256",
        "promotion_allowed", "live_mutation", "manifest_sha256",
    }
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        unsigned = dict(manifest)
        declared = str(unsigned.pop("manifest_sha256", ""))
        if (
            set(manifest) != expected_manifest_keys
            or canonical_sha256(unsigned) != declared
            or manifest.get("manifest_type") != "ndx_dynamic_shadow_nominal_open_close_evidence"
            or manifest.get("status") != "IMMUTABLE_EXACT_TICKER_SESSION_GRID"
            or manifest.get("valuation_end_date") != end.date().isoformat()
            or manifest.get("tickers") != tickers
            or file_sha256(data_path) != (manifest.get("artifact") or {}).get("sha256")
            or int((manifest.get("artifact") or {}).get("rows", -1))
            != len(tickers) * len(pd.to_datetime(sessions["session_date"]).loc[
                pd.to_datetime(sessions["session_date"]).le(end)
            ])
            or manifest.get("module_sha256") != file_sha256(
                ROOT / "backtest/ndx_dynamic_shadow_daily.py"
            )
            or manifest.get("script_sha256") != file_sha256(Path(__file__).resolve())
            or manifest.get("promotion_allowed") is not False
            or manifest.get("live_mutation") is not False
        ):
            raise NdxDynamicShadowDailyError("immutable nominal price evidence changed")
        sources = manifest.get("sources") or {}
        if set(sources) != set(tickers):
            raise NdxDynamicShadowDailyError("nominal source inventory ticker set changed")
        source_frames = []
        for ticker in tickers:
            item = sources[ticker]
            source_path = directory / "sources" / f"{ticker}.csv"
            if (
                set(item) != {
                    "filename", "rows", "sha256", "source_mode", "fallback_errors",
                    "data_start", "data_end",
                }
                or item.get("filename") != f"sources/{ticker}.csv"
                or not source_path.is_file()
                or file_sha256(source_path) != item.get("sha256")
            ):
                raise NdxDynamicShadowDailyError("nominal per-ticker source binding changed")
            source_frame = pd.read_csv(source_path)
            if len(source_frame) != int(item.get("rows", -1)):
                raise NdxDynamicShadowDailyError("nominal per-ticker source rows changed")
            source_frames.append(source_frame)
        rebuilt = validate_nominal_price_evidence(
            pd.concat(source_frames, ignore_index=True), sessions,
            tickers=tickers, valuation_end_date=end,
        )
        expected_content = rebuilt.assign(
            Date=rebuilt["Date"].dt.date.astype(str)
        ).to_csv(index=False, lineterminator="\n")
        if data_path.read_text(encoding="utf-8") != expected_content:
            raise NdxDynamicShadowDailyError("nominal combined artifact differs from frozen sources")
        long = rebuilt
    else:
        start = pd.Timestamp(sessions["session_date"].min()).normalize()
        source_frames = []
        sources = {}
        for ticker in tickers:
            frame, source_mode, errors = fetch_unadjusted_bars(
                ticker, begin=start, end=end,
            )
            frame = frame.loc[frame.index <= end]
            if not {"Open", "Close"}.issubset(frame.columns):
                raise NdxDynamicShadowDailyError(f"nominal source lacks Open/Close: {ticker}")
            source_frame = frame[["Open", "Close"]].reset_index()
            source_frame.columns = ["Date", "Open", "Close"]
            source_frame.insert(1, "ticker", ticker)
            source_frame = validate_nominal_price_evidence(
                source_frame, sessions, tickers=[ticker], valuation_end_date=end,
            )
            source_frames.append(source_frame)
            source_path = directory / "sources" / f"{ticker}.csv"
            source_content = source_frame.assign(
                Date=source_frame["Date"].dt.date.astype(str)
            ).to_csv(index=False, lineterminator="\n")
            source_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.exists() and source_path.read_text(encoding="utf-8") != source_content:
                raise NdxDynamicShadowDailyError(f"immutable nominal source collision: {ticker}")
            if not source_path.exists():
                temporary = source_path.with_suffix(".csv.tmp")
                temporary.write_text(source_content, encoding="utf-8", newline="\n")
                os.replace(temporary, source_path)
            sources[ticker] = {
                "filename": f"sources/{ticker}.csv",
                "rows": len(source_frame),
                "sha256": file_sha256(source_path),
                "source_mode": source_mode,
                "fallback_errors": errors,
                "data_start": source_frame["Date"].iloc[0].date().isoformat(),
                "data_end": source_frame["Date"].iloc[-1].date().isoformat(),
            }
        long = validate_nominal_price_evidence(
            pd.concat(source_frames, ignore_index=True), sessions,
            tickers=tickers, valuation_end_date=end,
        )
        directory.mkdir(parents=True, exist_ok=True)
        content = long.assign(Date=long["Date"].dt.date.astype(str)).to_csv(
            index=False, lineterminator="\n"
        )
        temporary = data_path.with_suffix(".csv.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, data_path)
        manifest = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_nominal_open_close_evidence",
            "status": "IMMUTABLE_EXACT_TICKER_SESSION_GRID",
            "valuation_end_date": end.date().isoformat(),
            "tickers": tickers,
            "price_basis": "UNADJUSTED_NOMINAL_TRADE_PRICE",
            "execution_field": "Open",
            "valuation_field": "Close",
            "sources": sources,
            "artifact": {"filename": data_path.name, "rows": len(long), "sha256": file_sha256(data_path)},
            "module_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_daily.py"),
            "script_sha256": file_sha256(Path(__file__).resolve()),
            "promotion_allowed": False,
            "live_mutation": False,
        }
        manifest["manifest_sha256"] = canonical_sha256(manifest)
        _atomic_json(manifest_path, manifest)
    long = validate_nominal_price_evidence(
        long, sessions, tickers=tickers, valuation_end_date=end,
    )
    index = pd.to_datetime(sessions["session_date"])
    opens = long.pivot(index="Date", columns="ticker", values="Open")
    closes = long.pivot(index="Date", columns="ticker", values="Close")
    opens.index = pd.to_datetime(opens.index)
    closes.index = pd.to_datetime(closes.index)
    opens = opens.reindex(index)
    closes = closes.reindex(index)
    evidence_hash = file_sha256(manifest_path)
    evidence_by_date = {value.date().isoformat(): evidence_hash for value in index if value <= end}
    return opens, closes, evidence_by_date


def verify_nominal_price_evidence_manifest(
    manifest_path: str | Path, sessions: pd.DataFrame,
) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    expected_root = PRICE_ROOT.resolve()
    if path.parent.parent != expected_root or path.name != "manifest.json":
        raise NdxDynamicShadowDailyError("nominal price evidence path is not canonical")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    end = str(manifest.get("valuation_end_date") or "")
    tickers = list(manifest.get("tickers") or [])
    _nominal_price_evidence(tickers, sessions, valuation_end_date=end)
    return json.loads(path.read_text(encoding="utf-8"))


def _frozen_original8_securities() -> list[dict[str, Any]]:
    load_frozen_original_8_definition(ORIGINAL8_MANIFEST)
    payload = json.loads(ORIGINAL8_MANIFEST.read_text(encoding="utf-8"))
    securities = list((payload.get("definition") or {}).get("securities") or [])
    if len(securities) != 8:
        raise NdxDynamicShadowDailyError("canonical original-8 definition is incomplete")
    return [dict(value) for value in securities]


def _target_source_snapshot(
    observed_at_utc: pd.Timestamp,
) -> tuple[pd.DataFrame, Path | None, Path | None, str | None, str | None, str, str | None]:
    """Freeze current canonical target bytes, or return an explicit pending input."""
    refresh_error = None
    try:
        _, refresh_meta = get_fund_nav(
            "012922", load_config(ROOT / "config/config.yaml"), refresh=True
        )
        if getattr(refresh_meta, "cached", False) or getattr(refresh_meta, "stale", False):
            refresh_error = json.dumps(
                getattr(refresh_meta, "errors", {}) or {"source": getattr(refresh_meta, "source", "")},
                ensure_ascii=False, sort_keys=True, default=str,
            )
    except Exception as exc:
        refresh_error = f"{type(exc).__name__}: {exc}"
    try:
        meta = json.loads(TARGET_MANIFEST.read_text(encoding="utf-8"))
        csv_hash = file_sha256(TARGET_CSV)
        manifest_hash = file_sha256(TARGET_MANIFEST)
        frame = pd.read_csv(TARGET_CSV)
        if (
            meta.get("dataset_key") != "012922"
            or meta.get("content_sha256") != csv_hash
            or int(meta.get("row_count", -1)) != len(frame)
            or meta.get("publication_time_known") is not False
            or pd.Timestamp(meta.get("fetched_at")).tzinfo is None
        ):
            raise NdxDynamicShadowDailyError("canonical 012922 manifest/content is invalid")
    except (OSError, json.JSONDecodeError, ValueError, TypeError, NdxDynamicShadowDailyError) as exc:
        return (
            pd.DataFrame(columns=["Date", "Close"]), None, None, None, None,
            observed_at_utc.isoformat(), refresh_error or f"{type(exc).__name__}: {exc}",
        )
    TARGET_SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    csv_snapshot = TARGET_SOURCE_ROOT / f"{csv_hash}.csv"
    manifest_snapshot = TARGET_SOURCE_ROOT / f"{manifest_hash}.manifest.json"
    for source, destination in ((TARGET_CSV, csv_snapshot), (TARGET_MANIFEST, manifest_snapshot)):
        if destination.exists() and file_sha256(destination) != file_sha256(source):
            raise NdxDynamicShadowDailyError("immutable 012922 source snapshot collision")
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
    return (
        frame, csv_snapshot, manifest_snapshot, csv_hash, manifest_hash,
        pd.Timestamp(meta["fetched_at"]).tz_convert("UTC").isoformat(), refresh_error,
    )


def _realize_ready_decisions(sessions: pd.DataFrame) -> int:
    realized = 0
    dispositions = {row["decision_date"] for row in _load_dispositions()}
    for decision_date in decision_coordinates(sessions):
        if decision_date in dispositions or len(_decision_paths(decision_date)) == 10:
            continue
        final_path = _final_manifest(decision_date)
        if not final_path.is_file():
            continue
        _verify_input_seal(decision_date)
        verify_final_role_seal_record(
            final_path, SEARCH_ROOT / "role_seals.jsonl",
            expected_final_root=SEARCH_ROOT / "final",
        )
        later = sessions.loc[pd.to_datetime(sessions["session_date"]).gt(pd.Timestamp(decision_date))]
        if later.empty:
            continue
        previous = _load_previous_heads(decision_date)
        decisions = build_realized_lane_decisions(
            final_path, sessions, previous_lane_heads=previous or None,
        )
        write_immutable_realized_decisions(REALIZED_ROOT, decisions)
        realized += 1
    return realized


def _append_all_lane_paths(sessions: pd.DataFrame) -> dict[str, Any]:
    lanes = _all_lane_decisions()
    if not lanes:
        return {
            "selector_lane_count": 0,
            "appended_selector_records": 0,
            "original_8_control_rows": 0,
            "target_012922_trace_rows": 0,
            "target_012922_pending_rows": 0,
            "three_way_alignment_manifest": None,
        }
    valuation_end = pd.Timestamp(sessions["session_date"].max()).date().isoformat()
    original_securities = _frozen_original8_securities()
    original_tickers = [str(value["ticker"]).upper() for value in original_securities]
    tickers = sorted(set(_selected_tickers(lanes)) | set(original_tickers))
    opens, closes, evidence = _nominal_price_evidence(
        tickers, sessions, valuation_end_date=valuation_end,
    )
    lane_count = appended = 0
    selector_paths: dict[str, Path] = {}
    path_dates: list[str] | None = None
    for selector_id, decisions in sorted(lanes.items()):
        _, rebalances, trades, path = replay_lane_path(
            decisions, sessions=sessions, valuation_closes=closes,
            execution_opens=opens, valuation_end_date=valuation_end,
        )
        ledger = PATH_ROOT / f"{selector_id}.jsonl"
        before = len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.is_file() else 0
        records = append_lane_path(
            ledger, selector_id=selector_id, path=path, rebalances=rebalances,
            trades=trades, price_evidence_sha256_by_date=evidence,
        )
        appended += len(records) - before
        lane_count += 1
        selector_paths[selector_id] = ledger
        dates = [str(value) for value in path["date"].tolist()]
        if path_dates is None:
            path_dates = dates
        elif dates != path_dates:
            raise NdxDynamicShadowDailyError("selector lanes do not share one valuation calendar")
    if lane_count != 10:
        raise NdxDynamicShadowDailyError("path update is not the complete 10-lane matrix")
    canonical_lane = lanes["strict_technology__return__v1"]
    _, original_rebalances, original_trades, original_path = replay_original8_control_path(
        canonical_lane,
        frozen_securities=original_securities,
        sessions=sessions,
        valuation_closes=closes,
        execution_opens=opens,
        valuation_end_date=valuation_end,
    )
    if original_path["date"].astype(str).tolist() != path_dates:
        raise NdxDynamicShadowDailyError("original-8 control calendar differs from selector lanes")
    append_lane_path(
        ORIGINAL8_LEDGER,
        selector_id="ndx_original_8_incumbent_v0",
        path=original_path,
        rebalances=original_rebalances,
        trades=original_trades,
        price_evidence_sha256_by_date=evidence,
    )
    observed_at = pd.Timestamp.now(tz="UTC")
    (
        target_nav, target_csv_snapshot, target_manifest_snapshot,
        target_csv_hash, target_manifest_hash, target_fetched_at, target_error,
    ) = _target_source_snapshot(observed_at)
    target_records = append_target_012922_trace(
        TARGET_TRACE_LEDGER,
        path_dates=path_dates or [],
        target_nav=target_nav,
        observed_at_utc=observed_at,
        source_csv_snapshot_path=target_csv_snapshot,
        source_manifest_snapshot_path=target_manifest_snapshot,
        source_csv_sha256=target_csv_hash,
        source_manifest_sha256=target_manifest_hash,
        source_fetched_at_utc=target_fetched_at,
    )
    alignment_dir = ALIGNMENT_ROOT / valuation_end
    alignment = write_three_way_calendar_manifest(
        alignment_dir,
        selector_lane_ledgers=selector_paths,
        original_8_ledger=ORIGINAL8_LEDGER,
        target_012922_ledger=TARGET_TRACE_LEDGER,
        observed_sessions=sessions,
        observed_calendar_manifest_path=CALENDAR_MANIFEST,
    )
    alignment_path = alignment_dir / "manifest.json"
    verify_three_way_calendar_manifest(
        alignment_path, require_current_calendar_manifest_hash=True
    )
    return {
        "selector_lane_count": lane_count,
        "appended_selector_records": appended,
        "original_8_control_rows": len(load_lane_path_ledger(
            ORIGINAL8_LEDGER, "ndx_original_8_incumbent_v0"
        )),
        "target_012922_trace_rows": len(target_records),
        "target_012922_pending_rows": sum(
            value["status"] == "TARGET_ASOF_UNAVAILABLE_PENDING"
            for value in target_records
        ),
        "target_012922_source_error": target_error,
        "three_way_alignment_manifest": {
            "path": alignment_path.resolve().as_posix(),
            "sha256": file_sha256(alignment_path),
            "calendar_rows": alignment["calendar_session_count"],
            "target_first_observed_trace_complete": alignment[
                "target_first_observed_trace_complete"
            ],
            "target_resolved_outcome_benchmark_ready": alignment[
                "target_resolved_outcome_benchmark_ready"
            ],
        },
    }


def _daily_artifact_inventory(path_update: Mapping[str, Any]) -> dict[str, Any]:
    def item(path: Path, *, rows: int | None = None) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        value = {"path": path.resolve().as_posix(), "sha256": file_sha256(path)}
        if rows is not None:
            value["rows"] = int(rows)
        return value

    lane_ledgers = {}
    for track in ("strict_technology", "technology_plus_adjacent"):
        for role in ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE"):
            selector_id = f"{track}__{role.lower()}__v1"
            path = PATH_ROOT / f"{selector_id}.jsonl"
            if path.is_file():
                lane_ledgers[selector_id] = item(
                    path, rows=len(load_lane_path_ledger(path, selector_id))
                )
    batch_manifests = {}
    for directory in sorted(REALIZED_ROOT.glob("*")) if REALIZED_ROOT.is_dir() else []:
        if directory.is_dir() and not directory.name.startswith("."):
            path = directory / "batch_manifest.json"
            if path.is_file():
                batch_manifests[directory.name] = item(path)
    alignment_value = path_update.get("three_way_alignment_manifest") or {}
    alignment_path = Path(str(alignment_value.get("path") or ""))
    nominal_path = (
        PRICE_ROOT / alignment_path.parent.name / "manifest.json"
        if alignment_value else Path()
    )
    return {
        "daily_contract": item(CONTRACT),
        "daily_engine": item(ROOT / "backtest/ndx_dynamic_shadow_daily.py"),
        "daily_script": item(Path(__file__).resolve()),
        "observed_calendar_manifest": item(CALENDAR_MANIFEST),
        "realized_batch_manifests": batch_manifests,
        "selector_lane_ledgers": lane_ledgers,
        "original_8_control_ledger": item(
            ORIGINAL8_LEDGER,
            rows=(
                len(load_lane_path_ledger(ORIGINAL8_LEDGER, "ndx_original_8_incumbent_v0"))
                if ORIGINAL8_LEDGER.is_file() else None
            ),
        ),
        "target_012922_trace_ledger": item(
            TARGET_TRACE_LEDGER,
            rows=(
                len(load_target_012922_trace_ledger(TARGET_TRACE_LEDGER))
                if TARGET_TRACE_LEDGER.is_file() else None
            ),
        ),
        "three_way_alignment_manifest": item(alignment_path) if alignment_value else None,
        "nominal_price_evidence_manifest": item(nominal_path) if alignment_value else None,
    }


def _verify_activation_before_execute() -> dict[str, Any]:
    """Rebuild the registration gate on every execution, not only at install time."""
    from backtest.ndx_dynamic_shadow_activation_v2 import verify_activation_v2_manifest

    return verify_activation_v2_manifest(
        ACTIVATION_V2_MANIFEST, repository_root=ROOT,
    )


def execute(*, max_search_jobs: int = 0) -> dict[str, Any]:
    _verify_activation_before_execute()
    before = _protected_hashes()
    _refresh_calendar()
    calendar, sessions = _calendar_sessions()
    phases = []
    dispositions = {row["decision_date"] for row in _load_dispositions()}
    for decision_date in decision_coordinates(sessions):
        input_path = _input_manifest(decision_date)
        final_path = _final_manifest(decision_date)
        final = None
        if final_path.is_file():
            _verify_input_seal(decision_date)
            try:
                verify_final_role_seal_record(
                    final_path, SEARCH_ROOT / "role_seals.jsonl",
                    expected_final_root=SEARCH_ROOT / "final",
                )
            except Exception:
                final = None
            else:
                final = verify_final_candidate_snapshot(final_path)
        phase = classify_daily_phase(
            sessions, decision_date=decision_date,
            now_utc=datetime.now(timezone.utc).isoformat(),
            input_snapshot_exists=input_path.is_file(),
            final_candidate_exists=final is not None,
            no_decision_disposition_exists=decision_date in dispositions,
            decisions_realized=len(_decision_paths(decision_date)) == 10,
            final_roles_sealed_at_utc=(final or {}).get("roles_sealed_at_utc"),
        )
        if phase == "SEAL_FRESH_PIT_INPUT":
            _run_checked(candidate_generator_command(decision_date))
            _verify_input_seal(decision_date)
            phase = "RESUME_ALL_K_FRESH_SEARCH"
        if phase == "RESUME_ALL_K_FRESH_SEARCH":
            _verify_input_seal(decision_date)
            decision_row = sessions.loc[sessions["session_date"].eq(pd.Timestamp(decision_date))].iloc[0]
            close_local = pd.Timestamp(decision_row["close_timestamp_utc"]).tz_convert("Asia/Shanghai")
            deadline_local = close_local.normalize() + pd.Timedelta(hours=21, minutes=30)
            remaining = (deadline_local.tz_convert("UTC") - pd.Timestamp.now(tz="UTC")).total_seconds()
            if remaining <= 0:
                _append_no_decision(decision_date, "FRESH_SEARCH_NOT_COMPLETE_BEFORE_CONSERVATIVE_OPEN")
                phase = "NO_DECISION_NO_BACKFILL"
            else:
                try:
                    _run_checked(
                        fresh_search_command(decision_date, max_jobs=max_search_jobs),
                        timeout_seconds=remaining,
                    )
                except NdxDynamicShadowDailyError as exc:
                    if "exceeded the pre-open" in str(exc):
                        _append_no_decision(decision_date, "FRESH_SEARCH_TIMEOUT_BEFORE_CONSERVATIVE_OPEN")
                        phase = "NO_DECISION_NO_BACKFILL"
                    else:
                        raise
                if phase != "NO_DECISION_NO_BACKFILL":
                    final = verify_final_candidate_snapshot(final_path) if final_path.is_file() else None
                    phase = (
                        "WAIT_FOR_NEXT_OBSERVED_SESSION"
                        if final is not None else "RESUME_ALL_K_FRESH_SEARCH"
                    )
        if phase == "NO_DECISION_NO_BACKFILL":
            _append_no_decision(decision_date, "MISSED_DECISION_OR_ROLE_SEAL_WINDOW")
            dispositions.add(decision_date)
        phases.append({"decision_date": decision_date, "phase": phase})
    realized = _realize_ready_decisions(sessions)
    path_update = _append_all_lane_paths(sessions)
    after = _protected_hashes()
    if before != after:
        raise NdxDynamicShadowDailyError("protected live files changed")
    result = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_daily_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "RESEARCH_DAILY_COMPLETE_TARGET_TRACE_PENDING"
            if path_update.get("target_012922_pending_rows", 0)
            else "RESEARCH_DAILY_COMPLETE"
        ),
        "calendar_manifest_sha256": file_sha256(CALENDAR_MANIFEST),
        "latest_observed_session": calendar.get("latest_session_date"),
        "decision_phases": phases,
        "realized_decision_batches": realized,
        "independent_lane_count": path_update["selector_lane_count"],
        "benchmark_control_count": 2 if path_update["selector_lane_count"] else 0,
        "appended_lane_path_records": path_update["appended_selector_records"],
        "original_8_control_rows": path_update["original_8_control_rows"],
        "target_012922_trace_rows": path_update["target_012922_trace_rows"],
        "target_012922_pending_rows": path_update["target_012922_pending_rows"],
        "target_012922_source_error": path_update.get("target_012922_source_error"),
        "three_way_alignment_manifest": path_update["three_way_alignment_manifest"],
        "research_artifacts": _daily_artifact_inventory(path_update),
        "single_instance_lock_used": True,
        "historical_candidate_replay_used": False,
        "retrospective_decision_backfill_used": False,
        "automation_registered": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    result["run_manifest_sha256"] = canonical_sha256(result)
    latest_path = ORCHESTRATOR_ROOT / "latest_run.json"
    _atomic_json(latest_path, result)
    verify_daily_run_manifest(latest_path, repository_root=ROOT)
    return result


def readiness() -> dict[str, Any]:
    result = build_daily_readiness(
        CONTRACT, calendar_manifest_path=CALENDAR_MANIFEST, repository_root=ROOT,
        as_of_utc=datetime.now(timezone.utc).isoformat(),
    )
    _atomic_json(ORCHESTRATOR_ROOT / "readiness.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research-only dynamic shadow daily orchestrator")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--readiness", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--max-search-jobs", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_search_jobs < 0:
        print("daily orchestrator fail-closed: --max-search-jobs cannot be negative", file=sys.stderr)
        return 2
    before = _protected_hashes()
    try:
        with single_instance_lock():
            if args.execute:
                from backtest.ndx_dynamic_shadow_activation_v2 import (
                    verify_activation_v2_manifest,
                )

                verify_activation_v2_manifest(
                    ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json",
                    repository_root=ROOT,
                )
                result = execute(max_search_jobs=args.max_search_jobs)
            else:
                result = readiness()
        if _protected_hashes() != before:
            raise NdxDynamicShadowDailyError("protected live files changed")
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_daily_failure",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "automation_registered": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        _atomic_json(ORCHESTRATOR_ROOT / "last_failure.json", failure)
        print(f"daily orchestrator fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "dynamic shadow daily | "
        f"status={result['status']} | automation_registered=False | promotion=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    load_lane_path_ledger,
    load_target_012922_trace_ledger,
    validate_nominal_price_evidence,
    verify_realized_decision_chain,
    verify_three_way_calendar_manifest,
    write_three_way_calendar_manifest,
