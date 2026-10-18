r"""Evaluate immutable challenger cohorts without promoting or mutating live state."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_challenger_forward_cohort import read_price_cache  # noqa: E402
from backtest.ndx_challenger_forward_evaluation import (  # noqa: E402
    annotate_paired_execution_evidence,
    evaluate_candidate_pair,
    summarize_forward_readiness,
    summarize_research_tracks,
)
from backtest.ndx_challenger_forward_registry import (  # noqa: E402
    validate_forward_spec,
    validate_registry_spec_binding,
)
from backtest.ndx_marginal_forward import read_cohort_index  # noqa: E402
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


def _artifact(path: Path, rows: int) -> dict:
    return {"path": path.as_posix(), "rows": rows, "sha256": file_sha256(path)}


def _archive_evaluation_run(
    *,
    output: Path,
    generated: datetime,
    artifacts: dict[str, tuple[Path, int]],
    base_payload: dict,
    cohort_index_path: Path,
) -> dict:
    """Preserve every evaluation output instead of relying on a mutable latest directory."""
    run_id = generated.strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = output / "evaluation_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    archived = {}
    for key, (source, rows) in artifacts.items():
        target = run_dir / source.name
        shutil.copy2(source, target)
        archived[key] = _artifact(target, rows)
    archive_payload = {
        **base_payload,
        "manifest_type": "ndx_challenger_forward_evaluation_run",
        "evaluation_run_id": run_id,
        "cohort_index": (
            {"path": cohort_index_path.as_posix(), "sha256": file_sha256(cohort_index_path)}
            if cohort_index_path.exists() else None
        ),
        "artifacts": archived,
    }
    manifest_path = run_dir / "manifest.json"
    atomic_write_text(manifest_path, json.dumps(archive_payload, ensure_ascii=False, indent=2) + "\n")
    return {"path": manifest_path.as_posix(), "sha256": file_sha256(manifest_path), "evaluation_run_id": run_id}


def _target_nav(path: Path) -> tuple[pd.DataFrame, dict]:
    sidecar = path.with_name(path.name + ".manifest.json")
    manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    if manifest.get("content_sha256") != file_sha256(path):
        raise ValueError("012922 target NAV hash mismatch")
    frame = pd.read_csv(path)
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    return frame.dropna(subset=["Date", "Close"]).drop_duplicates("Date").sort_values("Date").set_index("Date"), manifest


def load_shadow_contract(path: Path, *, spec_path: Path, registry_manifest_path: Path) -> dict:
    contract = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if int(contract.get("schema_version") or 0) != 1:
        raise ValueError("shadow monitoring schema changed")
    if contract.get("status") != "PRE_REGISTERED_EARLY_FALSIFICATION_ONLY_NOT_ADMISSION":
        raise ValueError("shadow monitoring status changed")
    if contract.get("source_forward_spec_sha256") != file_sha256(spec_path):
        raise ValueError("shadow monitoring forward spec identity changed")
    if contract.get("source_registry_manifest_sha256") != file_sha256(registry_manifest_path):
        raise ValueError("shadow monitoring registry identity changed")
    horizons = [int(value) for value in contract.get("monitoring_horizons_trading_days") or []]
    if horizons != [21, 63]:
        raise ValueError("shadow monitoring horizons must remain 21 and 63 trading days")
    if (
        contract.get("candidate_set_may_be_rewritten_from_shadow_results") is not False
        or contract.get("promotion_allowed") is not False
        or contract.get("live_mutation_allowed") is not False
    ):
        raise ValueError("shadow monitoring unexpectedly permits mutation or promotion")
    return contract


def summarize_shadow_monitoring(
    active: pd.DataFrame,
    shadow_evaluations: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    rows = []
    for entry in active.to_dict("records"):
        for horizon in horizons:
            if shadow_evaluations.empty:
                group = pd.DataFrame()
            else:
                group = shadow_evaluations.loc[
                    shadow_evaluations["registry_entry_id"].astype(str).eq(str(entry["registry_entry_id"]))
                    & pd.to_numeric(shadow_evaluations["monitoring_horizon_trading_days"]).eq(int(horizon))
                    & shadow_evaluations["fresh_oos_eligible"].astype(bool)
                ].copy()
            mature = group.loc[group["mature"].astype(bool)] if not group.empty else group
            if not mature.empty and "paired_execution_evidence_eligible" in mature.columns:
                executable = mature.loc[mature["paired_execution_evidence_eligible"].astype(bool)]
            else:
                executable = mature.loc[
                    mature["execution_status"].astype(str).eq("MATURE_EXECUTABLE")
                    & mature["cohort_execution_track_status"].astype(str).eq("COHORT_WHOLE_LOT_COMPLIANT")
                    & mature["original_8_cohort_execution_track_status"].astype(str).eq("COHORT_WHOLE_LOT_COMPLIANT")
                ] if not mature.empty else mature
            row = {
                "registry_entry_id": entry["registry_entry_id"],
                "candidate_id": entry["candidate_id"],
                "research_track": entry["research_track"],
                "holding_count_interpretation": entry["holding_count_interpretation"],
                "holding_count": len(str(entry["candidate_tickers"]).split(";")),
                "candidate_tickers": entry["candidate_tickers"],
                "monitoring_horizon_trading_days": int(horizon),
                "registered_fresh_cohorts": len(group),
                "mature_fresh_cohorts": len(mature),
                "executable_mature_fresh_cohorts": len(executable),
                "paired_execution_ineligible_mature_fresh_cohorts": len(mature) - len(executable),
                "paired_execution_evidence_statuses": (
                    ";".join(sorted(set(mature["paired_execution_evidence_status"].astype(str))))
                    if not mature.empty and "paired_execution_evidence_status" in mature.columns else ""
                ),
                "target_012922_mature_cohorts": (
                    int(mature["target_012922_mature"].astype(bool).sum()) if not mature.empty else 0
                ),
                "status": (
                    "EARLY_FALSIFICATION_EVIDENCE_AVAILABLE_NOT_ADMISSION"
                    if not mature.empty else "WAITING_FOR_SHADOW_HORIZON_MATURITY"
                ),
                "promotion_allowed": False,
            }
            if not mature.empty:
                for column in (
                    "continuous_return_delta_vs_original_8",
                    "continuous_drawdown_cost_vs_original_8",
                    "continuous_return_delta_vs_012922",
                    "continuous_drawdown_cost_vs_012922",
                ):
                    values = pd.to_numeric(mature[column], errors="coerce").dropna()
                    row[f"{column}_median"] = float(values.median()) if not values.empty else None
            if not executable.empty:
                for column in (
                    "execution_return_delta_vs_original_8",
                    "execution_drawdown_cost_vs_original_8",
                    "execution_return_delta_vs_012922",
                    "execution_drawdown_cost_vs_012922",
                ):
                    values = pd.to_numeric(executable[column], errors="coerce").dropna()
                    row[f"{column}_median"] = float(values.median()) if not values.empty else None
            rows.append(row)
    return pd.DataFrame(rows)


def shadow_horizon_diagnostics(
    shadow_evaluations: pd.DataFrame,
    horizons: list[int],
) -> list[dict]:
    """Expose maturity progress without mixing portfolio and migration tracks."""
    diagnostics = []
    for horizon in horizons:
        if shadow_evaluations.empty:
            group = pd.DataFrame()
        else:
            group = shadow_evaluations.loc[
                pd.to_numeric(
                    shadow_evaluations["monitoring_horizon_trading_days"], errors="raise"
                ).eq(int(horizon))
                & shadow_evaluations["fresh_oos_eligible"].astype(bool)
            ].copy()
        available = (
            pd.to_numeric(group["available_common_sessions"], errors="raise")
            if not group.empty else pd.Series(dtype="int64")
        )
        minimum_available = int(available.min()) if not available.empty else 0
        mature = group.loc[group["mature"].astype(bool)] if not group.empty else group
        track_rows = {
            track: int(track_group["mature"].astype(bool).sum())
            for track, track_group in group.groupby("research_track", sort=True)
        } if not group.empty else {}
        diagnostics.append({
            "horizon_trading_days": int(horizon),
            "fresh_evaluation_rows": int(len(group)),
            "available_common_sessions_min": (
                int(available.min()) if not available.empty else None
            ),
            "available_common_sessions_max": (
                int(available.max()) if not available.empty else None
            ),
            "sessions_remaining_until_all_rows_mature": max(
                0, int(horizon) - minimum_available
            ),
            "mature_evaluation_rows": int(len(mature)),
            "target_012922_mature_rows": (
                int(mature["target_012922_mature"].astype(bool).sum())
                if not mature.empty else 0
            ),
            "mature_rows_by_research_track": track_rows,
            "statuses": (
                sorted(set(group["status"].astype(str))) if not group.empty else []
            ),
            "promotion_allowed": False,
        })
    return diagnostics


def validate_cohort_evaluation_identity(
    manifest: dict,
    index_record: dict,
    *,
    spec_path: Path,
    registry_manifest_path: Path,
    registry_content_sha256: str,
    active_candidate_count: int,
) -> dict[str, tuple[Path, int]]:
    """Fail closed when a frozen cohort no longer matches its preregistered inputs."""
    if manifest.get("manifest_type") != "ndx_challenger_forward_cohort":
        raise ValueError("cohort manifest type changed")
    for key in ("observation_date", "fresh_oos_eligible", "cohort_origin", "active_candidate_count"):
        if manifest.get(key) != index_record.get(key):
            raise ValueError(f"cohort index identity changed: {key}")
    if int(manifest.get("active_candidate_count", -1)) != int(active_candidate_count):
        raise ValueError("cohort active candidate count differs from current frozen registry")

    inputs = manifest.get("inputs") or {}
    for key, current_path in (("spec", spec_path), ("registry_manifest", registry_manifest_path)):
        item = inputs.get(key) or {}
        frozen_path = Path(str(item.get("path") or ""))
        if frozen_path.resolve() != current_path.resolve() or item.get("sha256") != file_sha256(current_path):
            raise ValueError(f"cohort frozen input changed: {key}")
    if inputs.get("registry_content_sha256") != registry_content_sha256:
        raise ValueError("cohort frozen registry content changed")

    validated: dict[str, tuple[Path, int]] = {}
    index_hash_keys = {
        "cohort_candidates": "cohort_candidates_sha256",
        "cohort_positions": "cohort_positions_sha256",
    }
    for key, index_hash_key in index_hash_keys.items():
        artifact = (manifest.get("artifacts") or {}).get(key) or {}
        path = Path(str(artifact.get("path") or ""))
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"cohort artifact path invalid: {key}")
        actual_sha256 = file_sha256(path)
        if artifact.get("sha256") != actual_sha256 or index_record.get(index_hash_key) != actual_sha256:
            raise ValueError(f"cohort artifact changed: {key}")
        rows = int(artifact.get("rows", -1))
        if rows < 0:
            raise ValueError(f"cohort artifact row count invalid: {key}")
        validated[key] = (path, rows)
    return validated


def _regime(qqq: pd.DataFrame, observation_date: str) -> str:
    history = qqq.loc[qqq.index <= pd.Timestamp(observation_date), "Close"].tail(200)
    if len(history) < 200:
        return "INSUFFICIENT_HISTORY"
    close = float(history.iloc[-1])
    above50 = close >= float(history.tail(50).mean())
    above200 = close >= float(history.mean())
    return "BULL" if above50 and above200 else ("BEAR" if not above50 and not above200 else "TRANSITION")


def run(args: argparse.Namespace) -> dict:
    spec_path = _resolve(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    validate_forward_spec(spec)
    forward = spec["forward_contract"]
    output = _resolve(args.output_dir)
    registry_manifest_path = _resolve(args.registry_manifest)
    registry_manifest = json.loads(registry_manifest_path.read_text(encoding="utf-8"))
    validate_registry_spec_binding(
        registry_manifest, spec, spec_sha256=file_sha256(spec_path),
    )
    shadow_spec_path = _resolve(args.shadow_spec)
    shadow_contract = load_shadow_contract(
        shadow_spec_path, spec_path=spec_path, registry_manifest_path=registry_manifest_path,
    )
    shadow_horizons = [int(value) for value in shadow_contract["monitoring_horizons_trading_days"]]
    active_item = registry_manifest["artifacts"]["active_registry"]
    active_path = Path(active_item["path"])
    if file_sha256(active_path) != active_item["sha256"]:
        raise ValueError("active forward registry hash mismatch")
    active = pd.read_csv(active_path, low_memory=False, keep_default_na=False)
    cohort_index_path = output / "cohort_index.jsonl"
    index = read_cohort_index(cohort_index_path)
    evaluations = []
    shadow_evaluations = []
    target_manifest = None
    price_inputs: dict[str, dict] = {}
    if index:
        target, target_manifest = _target_nav(_resolve(args.target_nav))
        qqq_path = _resolve(args.price_cache_dir) / "QQQ.csv"
        qqq = read_price_cache(qqq_path)
        price_inputs["QQQ"] = {"path": qqq_path.as_posix(), "sha256": file_sha256(qqq_path)}
        for record in index:
            manifest_path = Path(record["cohort_manifest_path"])
            if file_sha256(manifest_path) != record["cohort_manifest_sha256"]:
                raise ValueError(f"cohort manifest changed: {manifest_path}")
            cohort_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = validate_cohort_evaluation_identity(
                cohort_manifest,
                record,
                spec_path=spec_path,
                registry_manifest_path=registry_manifest_path,
                registry_content_sha256=active_item["sha256"],
                active_candidate_count=len(active),
            )
            candidate_path, candidate_rows = artifacts["cohort_candidates"]
            positions_path, position_rows = artifacts["cohort_positions"]
            candidates = pd.read_csv(candidate_path, low_memory=False, keep_default_na=False)
            positions = pd.read_csv(positions_path, low_memory=False, keep_default_na=False)
            if len(candidates) != candidate_rows or len(positions) != position_rows:
                raise ValueError(f"cohort artifact row count changed: {manifest_path}")
            challengers = candidates.loc[candidates["track_role"].eq("CHALLENGER")].copy()
            controls = candidates.loc[candidates["track_role"].eq("ORIGINAL_8_CONTROL")].copy()
            if len(challengers) != len(active) or len(controls) != 1 or len(candidates) != len(active) + 1:
                raise ValueError(f"cohort candidate/control rows differ from frozen registry contract: {manifest_path}")
            control = positions.loc[positions["track_role"].eq("ORIGINAL_8_CONTROL")].copy()
            if control.empty or control["registry_entry_id"].astype(str).nunique() != 1:
                raise ValueError(f"cohort original-8 control positions are incomplete: {manifest_path}")
            control_row = controls.iloc[0]
            for candidate in challengers.to_dict("records"):
                candidate_positions = positions.loc[positions["registry_entry_id"].astype(str).eq(str(candidate["registry_entry_id"]))].copy()
                tickers = sorted(set(candidate_positions["ticker"].astype(str)).union(control["ticker"].astype(str)))
                prices = {}
                for ticker in tickers:
                    path = _resolve(args.price_cache_dir) / f"{ticker}.csv"
                    prices[ticker] = read_price_cache(path)
                    price_inputs[ticker] = {"path": path.as_posix(), "sha256": file_sha256(path)}
                result = evaluate_candidate_pair(
                    candidate_positions, control, prices,
                    observation_date=str(record["observation_date"]),
                    horizon=int(forward["primary_horizon_trading_days"]),
                    standardized_cash=float(forward["standardized_execution_cash_usd"]),
                    minimum_cash_buffer=float(forward["minimum_cash_buffer_usd"]),
                    transaction_cost_bps=float(forward["transaction_cost_bps"]),
                    target_nav=target,
                )
                identity = {
                    "registry_entry_id": candidate["registry_entry_id"], "candidate_id": candidate["candidate_id"],
                    "selection_role": candidate["selection_role"], "action_scope": candidate["action_scope"],
                    "research_track": candidate["research_track"],
                    "holding_count_interpretation": candidate["holding_count_interpretation"],
                    "holding_count": candidate["holding_count"],
                    "candidate_tickers": candidate["candidate_tickers"],
                    "frozen_target_weights": candidate["frozen_target_weights"],
                    "selection_rationale": candidate["selection_rationale"],
                    "cohort_execution_track_status": candidate["execution_track_status"],
                    "cohort_execution_constraint_failures": candidate["execution_constraint_failures"],
                    "original_8_cohort_execution_track_status": control_row["execution_track_status"],
                    "original_8_cohort_execution_constraint_failures": control_row["execution_constraint_failures"],
                    "fresh_oos_eligible": bool(record["fresh_oos_eligible"]),
                    "observation_regime": _regime(qqq, str(record["observation_date"])),
                }
                evaluation_row = {**identity, **result}
                evaluations.append({
                    **evaluation_row, **annotate_paired_execution_evidence(evaluation_row),
                })
                for shadow_horizon in shadow_horizons:
                    shadow_result = evaluate_candidate_pair(
                        candidate_positions, control, prices,
                        observation_date=str(record["observation_date"]),
                        horizon=shadow_horizon,
                        standardized_cash=float(forward["standardized_execution_cash_usd"]),
                        minimum_cash_buffer=float(forward["minimum_cash_buffer_usd"]),
                        transaction_cost_bps=float(forward["transaction_cost_bps"]),
                        target_nav=target,
                    )
                    shadow_row = {
                        **identity,
                        "monitoring_horizon_trading_days": shadow_horizon,
                        "evidence_interpretation": shadow_contract["interpretation"],
                        **shadow_result,
                    }
                    shadow_evaluations.append({
                        **shadow_row, **annotate_paired_execution_evidence(shadow_row),
                    })
    evaluation = pd.DataFrame(evaluations)
    shadow_evaluation = pd.DataFrame(shadow_evaluations)
    summary = summarize_forward_readiness(active, evaluation, forward, spec["promotion_contract"])
    track_summary = summarize_research_tracks(summary)
    shadow_summary = summarize_shadow_monitoring(active, shadow_evaluation, shadow_horizons)
    shadow_diagnostics = shadow_horizon_diagnostics(shadow_evaluation, shadow_horizons)
    report_dir = output / "latest_evaluation"
    report_dir.mkdir(parents=True, exist_ok=True)
    evaluation_path = report_dir / "cohort_evaluations.csv"
    summary_path = report_dir / "maturity_summary.csv"
    track_summary_path = report_dir / "research_track_summary.csv"
    shadow_evaluation_path = report_dir / "shadow_evaluations.csv"
    shadow_summary_path = report_dir / "shadow_summary.csv"
    price_path = report_dir / "price_inputs.csv"
    _atomic_csv(evaluation, evaluation_path)
    _atomic_csv(summary, summary_path)
    _atomic_csv(track_summary, track_summary_path)
    _atomic_csv(shadow_evaluation, shadow_evaluation_path)
    _atomic_csv(shadow_summary, shadow_summary_path)
    _atomic_csv(pd.DataFrame([{"ticker": ticker, **detail} for ticker, detail in sorted(price_inputs.items())]), price_path)
    generated = datetime.now(timezone.utc)
    base_payload = {
        "schema_version": 1, "manifest_type": "ndx_challenger_forward_evaluation",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "status": "WAITING_FOR_FRESH_FORWARD_COHORTS" if not index else "FORWARD_MONITORING_NOT_ADMISSION",
        "registered_cohorts": len(index), "fresh_oos_cohorts": sum(bool(row["fresh_oos_eligible"]) for row in index),
        "mature_evaluation_rows": int(evaluation["mature"].astype(bool).sum()) if not evaluation.empty else 0,
        "portfolio_optimization_active_candidates": int(active["research_track"].astype(str).eq("portfolio_optimization").sum()),
        "migration_control_active_candidates": int(active["research_track"].astype(str).eq("migration_control").sum()),
        "policy_gate_ready_count": int(summary["policy_gate_ready"].astype(bool).sum()),
        "policy_gate_passed_count": int(summary["policy_gate_passed"].astype(bool).sum()),
        "candidate_admission_count": 0, "promotion_allowed": False,
        "shadow_monitoring_horizons_trading_days": shadow_horizons,
        "shadow_mature_evaluation_rows": (
            int(shadow_evaluation["mature"].astype(bool).sum()) if not shadow_evaluation.empty else 0
        ),
        "shadow_horizon_diagnostics": shadow_diagnostics,
        "shadow_evidence_interpretation": shadow_contract["interpretation"],
        "return_data_read": bool(index), "live_config_changed": False, "state_changed": False, "today_advice_changed": False,
        "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
        "registry_manifest": {"path": registry_manifest_path.as_posix(), "sha256": file_sha256(registry_manifest_path)},
        "shadow_spec": {"path": shadow_spec_path.as_posix(), "sha256": file_sha256(shadow_spec_path)},
        "target_012922_version": None if target_manifest is None else {"path": _resolve(args.target_nav).as_posix(), "sha256": file_sha256(_resolve(args.target_nav)), "version_id": target_manifest.get("version_id")},
    }
    artifact_sources = {
        "evaluations": (evaluation_path, len(evaluation)),
        "summary": (summary_path, len(summary)),
        "research_track_summary": (track_summary_path, len(track_summary)),
        "shadow_evaluations": (shadow_evaluation_path, len(shadow_evaluation)),
        "shadow_summary": (shadow_summary_path, len(shadow_summary)),
        "price_inputs": (price_path, len(price_inputs)),
    }
    immutable_run = _archive_evaluation_run(
        output=output, generated=generated, artifacts=artifact_sources,
        base_payload=base_payload, cohort_index_path=cohort_index_path,
    )
    payload = {
        **base_payload,
        "immutable_evaluation_run": immutable_run,
        "artifacts": {key: _artifact(path, rows) for key, (path, rows) in artifact_sources.items()},
    }
    atomic_write_text(report_dir / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估纯美股 challenger 不可变前向 cohort")
    parser.add_argument("--spec", default="config/ndx_challenger_forward_v3.yaml")
    parser.add_argument("--registry-manifest", default="data/cache/research/ndx_challenger_forward_registry_v3/manifest.json")
    parser.add_argument("--shadow-spec", default="config/ndx_challenger_shadow_v1.yaml")
    parser.add_argument("--price-cache-dir", default="data/cache")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_challenger_forward_v3")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"challenger 前向评价失败关闭: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"challenger 前向评价 | cohorts={payload['registered_cohorts']} | fresh={payload['fresh_oos_cohorts']} | mature_rows={payload['mature_evaluation_rows']} | admitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
