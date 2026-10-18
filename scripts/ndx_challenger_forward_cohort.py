r"""Plan or register immutable monthly cohorts for the pure-equity challengers."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_challenger_forward_cohort import (  # noqa: E402
    NdxChallengerForwardCohortError,
    build_cohort_snapshot,
    next_fresh_monthly_observation,
    observation_liquidity,
    read_price_cache,
    validate_observation,
)
from backtest.ndx_challenger_forward_registry import (  # noqa: E402
    validate_forward_spec,
    validate_registry_spec_binding,
)
from backtest.ndx_marginal_forward import append_cohort_index, read_cohort_index  # noqa: E402
from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256  # noqa: E402


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_registry(manifest_path: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "ndx_pure_equity_challenger_forward_registry":
        raise NdxChallengerForwardCohortError("unexpected challenger registry manifest")
    frames = []
    for key in ("active_registry", "risk_chain_map", "baseline"):
        item = (manifest.get("artifacts") or {}).get(key) or {}
        path = Path(str(item.get("path") or ""))
        if not path.is_absolute() or file_sha256(path) != item.get("sha256"):
            raise NdxChallengerForwardCohortError(f"registry artifact mismatch: {key}")
        frame = pd.read_csv(path, low_memory=False, keep_default_na=False)
        if len(frame) != int(item.get("rows") or -1):
            raise NdxChallengerForwardCohortError(f"registry artifact rows changed: {key}")
        frames.append(frame)
    return manifest, frames[0], frames[1], frames[2]


def _sessions(path: Path) -> pd.DatetimeIndex:
    frame = pd.read_csv(path, usecols=["Date"])
    return pd.DatetimeIndex(pd.to_datetime(frame["Date"], errors="coerce").dropna()).normalize().sort_values().unique()


def _missing_observation_close_tickers(
    price_dir: Path,
    tickers: list[str],
    observation_date: str,
) -> list[str]:
    observed = pd.Timestamp(observation_date).normalize()
    missing = []
    for ticker in tickers:
        path = price_dir / f"{ticker}.csv"
        try:
            sessions = _sessions(path)
        except (FileNotFoundError, OSError, ValueError, pd.errors.EmptyDataError):
            missing.append(ticker)
            continue
        if observed not in sessions:
            missing.append(ticker)
    return missing


def registration_date_for(
    *, imported_seed: bool, override: str | None, now: datetime | None = None,
) -> str:
    """Bind fresh registration to the actual New York calendar date.

    A caller may only override the date for an explicitly imported historical
    seed, which is permanently ineligible for fresh-OOS credit.
    """
    if override and not imported_seed:
        raise NdxChallengerForwardCohortError(
            "--registered-date is only allowed with --imported-seed; fresh registration uses the current New York date"
        )
    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return override or current.date().isoformat()


def validate_existing_cohort_manifest(
    manifest: dict,
    *,
    observation: dict,
    cohort_path: Path,
    positions_path: Path,
    cohort_rows: int,
    position_rows: int,
    spec_path: Path,
    registry_path: Path,
    registry_content_sha256: str,
) -> None:
    """Reject a partially rewritten cohort before it can re-enter the index."""
    if manifest.get("manifest_type") != "ndx_challenger_forward_cohort":
        raise NdxChallengerForwardCohortError("existing cohort manifest type changed")
    for key in ("observation_date", "registered_date", "cohort_origin", "fresh_oos_eligible"):
        if manifest.get(key) != observation.get(key):
            raise NdxChallengerForwardCohortError(f"existing cohort identity changed: {key}")
    expected_artifacts = {
        "cohort_candidates": (cohort_path.resolve(), cohort_rows),
        "cohort_positions": (positions_path.resolve(), position_rows),
    }
    for key, (path, rows) in expected_artifacts.items():
        artifact = (manifest.get("artifacts") or {}).get(key) or {}
        if Path(str(artifact.get("path") or "")) != path:
            raise NdxChallengerForwardCohortError(f"existing cohort artifact path changed: {key}")
        if int(artifact.get("rows") or -1) != rows or artifact.get("sha256") != file_sha256(path):
            raise NdxChallengerForwardCohortError(f"existing cohort artifact changed: {key}")
    inputs = manifest.get("inputs") or {}
    for key, path in (("spec", spec_path), ("registry_manifest", registry_path)):
        item = inputs.get(key) or {}
        if Path(str(item.get("path") or "")) != path or item.get("sha256") != file_sha256(path):
            raise NdxChallengerForwardCohortError(f"existing cohort input changed: {key}")
    if inputs.get("registry_content_sha256") != registry_content_sha256:
        raise NdxChallengerForwardCohortError("existing cohort registry content changed")


def plan(args: argparse.Namespace) -> dict:
    spec_path = _resolve(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    validate_forward_spec(spec)
    registry_path = _resolve(args.registry_manifest)
    registry, active, risk_map, baseline = _load_registry(registry_path)
    validate_registry_spec_binding(
        registry, spec, spec_sha256=file_sha256(spec_path),
    )
    output = _resolve(args.output_dir)
    index = read_cohort_index(output / "cohort_index.jsonl")
    qqq_path = _resolve(args.price_cache_dir) / "QQQ.csv"
    sessions = _sessions(qqq_path)
    previous = [str(row["observation_date"]) for row in index]
    not_before = str(spec["forward_contract"]["first_fresh_observation_on_or_after"])
    if previous:
        not_before = (pd.Timestamp(previous[-1]) + pd.offsets.MonthBegin()).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    expected, skipped_expired = next_fresh_monthly_observation(sessions, not_before, today)
    same_day_candidate = bool(expected and expected == today)
    price_dir = _resolve(args.price_cache_dir)
    tickers = sorted(set(risk_map["ticker"].astype(str)).union(set(baseline["ticker"].astype(str))))
    missing_close_tickers = (
        _missing_observation_close_tickers(price_dir, tickers, str(expected))
        if same_day_candidate else []
    )
    ready = same_day_candidate and not missing_close_tickers
    status = "WAITING_FOR_COMPLETED_MONTHLY_COHORT_SESSION"
    if same_day_candidate and missing_close_tickers:
        status = "WAITING_FOR_COMPLETE_OBSERVATION_CLOSE_COVERAGE"
    elif ready:
        status = "READY_FOR_SAME_DAY_POST_CLOSE_REGISTRATION"
    payload = {
        "schema_version": 1, "manifest_type": "ndx_challenger_forward_cohort_readiness",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "latest_completed_qqq_session": sessions[-1].strftime("%Y-%m-%d") if len(sessions) else None,
        "next_expected_observation_if_already_cached": expected,
        "expired_monthly_observations_skipped_without_backfill": skipped_expired,
        "observation_close_coverage_checked": same_day_candidate,
        "observation_close_coverage_complete": ready if same_day_candidate else None,
        "missing_observation_close_tickers": missing_close_tickers,
        "registered_cohorts": len(index), "fresh_oos_cohorts": sum(bool(row.get("fresh_oos_eligible")) for row in index),
        "active_candidates": len(active), "risk_chain_rows": len(risk_map), "baseline_positions": len(baseline),
        "standardized_execution_cash_usd": spec["forward_contract"]["standardized_execution_cash_usd"],
        "real_account_purchasing_power_required": False,
        "return_data_read": False, "observation_close_date_columns_read": same_day_candidate,
        "observation_close_values_read": False, "future_entry_price_values_read": False,
        "cohort_written": False, "promotion_allowed": False, "live_config_changed": False,
        "state_changed": False, "today_advice_changed": False,
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "registry_manifest": {"path": registry_path.as_posix(), "sha256": file_sha256(registry_path)},
            "qqq_calendar": {"path": qqq_path.as_posix(), "sha256": file_sha256(qqq_path), "date_column_only": True},
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output / "readiness.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def register(args: argparse.Namespace) -> dict:
    if not args.observation_date:
        raise NdxChallengerForwardCohortError("--observation-date is required for register")
    registered_date = registration_date_for(
        imported_seed=bool(args.imported_seed), override=args.registered_date,
    )
    spec_path = _resolve(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    validate_forward_spec(spec)
    registry_path = _resolve(args.registry_manifest)
    registry_manifest, active, risk_map, baseline = _load_registry(registry_path)
    validate_registry_spec_binding(
        registry_manifest, spec, spec_sha256=file_sha256(spec_path),
    )
    output = _resolve(args.output_dir)
    index_path = output / "cohort_index.jsonl"
    index = read_cohort_index(index_path)
    price_dir = _resolve(args.price_cache_dir)
    qqq_sessions = _sessions(price_dir / "QQQ.csv")
    observation = validate_observation(
        args.observation_date, registered_date, qqq_sessions,
        first_not_before=str(spec["forward_contract"]["first_fresh_observation_on_or_after"]),
        previous_observations=[str(row["observation_date"]) for row in index],
        imported_seed=bool(args.imported_seed),
    )
    tickers = sorted(set(risk_map["ticker"].astype(str)).union(set(baseline["ticker"].astype(str))))
    closes: dict[str, float] = {}
    liquidity: dict[str, float] = {}
    price_inputs = []
    observed_ts = pd.Timestamp(args.observation_date)
    for ticker in tickers:
        path = price_dir / f"{ticker}.csv"
        frame = read_price_cache(path)
        if observed_ts not in frame.index:
            raise NdxChallengerForwardCohortError(f"completed observation close missing: {ticker}")
        closes[ticker] = float(frame.loc[observed_ts, "Close"])
        liquidity_detail = observation_liquidity(
            frame, args.observation_date,
            lookback=int(spec["forward_contract"]["liquidity_lookback_trading_days"]),
            minimum_observations=int(spec["forward_contract"]["minimum_liquidity_observations"]),
        )
        liquidity[ticker] = float(liquidity_detail["median_dollar_volume_usd"])
        price_inputs.append({
            "ticker": ticker, "path": path.resolve().as_posix(), "sha256": file_sha256(path),
            "observation_close": closes[ticker], **liquidity_detail,
        })
    cohort, positions = build_cohort_snapshot(active, risk_map, baseline, closes, liquidity, spec, observation)
    cohort_dir = output / "observations" / args.observation_date
    cohort_path = cohort_dir / "cohort_candidates.csv"
    positions_path = cohort_dir / "cohort_positions.csv"
    manifest_path = cohort_dir / "manifest.json"
    if cohort_dir.exists():
        if not all(path.exists() for path in (cohort_path, positions_path, manifest_path)):
            raise NdxChallengerForwardCohortError("partial immutable cohort directory already exists")
        existing_cohort = pd.read_csv(cohort_path, low_memory=False, keep_default_na=False)
        existing_positions = pd.read_csv(positions_path, low_memory=False, keep_default_na=False)
        if existing_cohort.fillna("").to_dict("records") != cohort.fillna("").to_dict("records") or existing_positions.fillna("").to_dict("records") != positions.fillna("").to_dict("records"):
            raise NdxChallengerForwardCohortError("immutable cohort already exists with different evidence")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_existing_cohort_manifest(
            manifest,
            observation=observation,
            cohort_path=cohort_path,
            positions_path=positions_path,
            cohort_rows=len(cohort),
            position_rows=len(positions),
            spec_path=spec_path,
            registry_path=registry_path,
            registry_content_sha256=registry_manifest["artifacts"]["active_registry"]["sha256"],
        )
    else:
        cohort_dir.mkdir(parents=True)
        _atomic_csv(cohort, cohort_path)
        _atomic_csv(positions, positions_path)
        manifest = {
            "schema_version": 1, "manifest_type": "ndx_challenger_forward_cohort",
            **observation, "registered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "active_candidate_count": len(active), "same_date_original_8_control_count": 1,
            "execution_compliant_count": int(cohort["execution_track_status"].eq("COHORT_WHOLE_LOT_COMPLIANT").sum()),
            "execution_noncompliant_count": int(cohort["execution_track_status"].eq("COHORT_WHOLE_LOT_NONCOMPLIANT").sum()),
            "historical_whole_lot_shares_reused": False, "return_data_read": False,
            "observation_close_values_read": True, "future_entry_price_values_read": False,
            "entry_convention": spec["forward_contract"]["entry"], "promotion_allowed": False,
            "live_config_changed": False, "state_changed": False, "today_advice_changed": False,
            "inputs": {
                "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
                "registry_manifest": {"path": registry_path.as_posix(), "sha256": file_sha256(registry_path)},
                "registry_content_sha256": registry_manifest["artifacts"]["active_registry"]["sha256"],
                "prices": price_inputs,
            },
            "artifacts": {
                "cohort_candidates": {"path": cohort_path.resolve().as_posix(), "rows": len(cohort), "sha256": file_sha256(cohort_path)},
                "cohort_positions": {"path": positions_path.resolve().as_posix(), "rows": len(positions), "sha256": file_sha256(positions_path)},
            },
        }
        atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    record = append_cohort_index(index_path, {
        "schema_version": 1, "observation_date": args.observation_date,
        "fresh_oos_eligible": bool(manifest["fresh_oos_eligible"]), "cohort_origin": manifest["cohort_origin"],
        "cohort_manifest_path": manifest_path.resolve().as_posix(), "cohort_manifest_sha256": file_sha256(manifest_path),
        "cohort_candidates_sha256": file_sha256(cohort_path), "cohort_positions_sha256": file_sha256(positions_path),
        "active_candidate_count": len(active),
    })
    return {"manifest": manifest, "index_record": record}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纯美股 challenger 月度前向 cohort")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "register"):
        child = sub.add_parser(name)
        child.add_argument("--spec", default="config/ndx_challenger_forward_v3.yaml")
        child.add_argument("--registry-manifest", default="data/cache/research/ndx_challenger_forward_registry_v3/manifest.json")
        child.add_argument("--price-cache-dir", default="data/cache")
        child.add_argument("--output-dir", default="data/cache/research/ndx_challenger_forward_v3")
    register_parser = sub.choices["register"]
    register_parser.add_argument("--observation-date")
    register_parser.add_argument("--registered-date")
    register_parser.add_argument("--imported-seed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = plan(args) if args.command == "plan" else register(args)
    except (NdxChallengerForwardCohortError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"challenger 前向 cohort 失败关闭: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.command == "plan":
        print(f"challenger cohort readiness | status={result['status']} | latest={result['latest_completed_qqq_session']} | registered={result['registered_cohorts']}")
    else:
        manifest = result["manifest"]
        print(f"challenger cohort registered | date={manifest['observation_date']} | fresh={manifest['fresh_oos_eligible']} | admitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
