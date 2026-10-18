r"""Freeze the pure-equity challenger set for future-only evaluation."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_challenger_forward_registry import build_forward_registry, validate_forward_spec
from core.helpers import atomic_write_text
from data.versioning import file_sha256
from scripts.ndx_cardinality_frontier_attribution import INCUMBENT


def _resolve(value: str) -> Path:
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


def _validated_registry_lineage(spec: dict) -> dict | None:
    registry_id = str(spec.get("registry_id") or "")
    if not registry_id.endswith("_v5"):
        return None
    lineage = spec.get("registry_lineage") or {}
    if not isinstance(lineage, dict):
        raise ValueError("v5 registry lineage is invalid")
    predecessor_path = _resolve(str(lineage.get("predecessor_manifest") or ""))
    expected_sha256 = str(lineage.get("predecessor_manifest_sha256") or "")
    if (
        lineage.get("predecessor_registry_and_cohorts_immutable") is not True
        or lineage.get("candidate_identity_and_weights_carried_forward") is not True
        or not predecessor_path.is_file()
        or file_sha256(predecessor_path) != expected_sha256
    ):
        raise ValueError("v5 predecessor registry evidence mismatch")
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    locked_spec = ((predecessor.get("inputs") or {}).get("spec") or {}).get("sha256")
    if (
        predecessor.get("manifest_type") != "ndx_pure_equity_challenger_forward_registry"
        or predecessor.get("registry_id") != lineage.get("predecessor_registry_id")
        or locked_spec != lineage.get("predecessor_locked_spec_sha256")
        or predecessor.get("promotion_allowed") is not False
    ):
        raise ValueError("v5 predecessor registry identity mismatch")
    return {
        **lineage,
        "predecessor_manifest": predecessor_path.as_posix(),
        "predecessor_manifest_sha256": expected_sha256,
    }


def _manifest_artifact(manifest_path: Path, expected_type: str, key: str) -> tuple[Path, pd.DataFrame]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != expected_type:
        raise ValueError(f"unexpected source manifest: {manifest_path}")
    artifact = (manifest.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or file_sha256(path) != artifact.get("sha256"):
        raise ValueError(f"source artifact mismatch: {manifest_path}/{key}")
    frame = pd.read_csv(path, low_memory=False, keep_default_na=False)
    if len(frame) != int(artifact.get("rows") or -1):
        raise ValueError(f"source artifact rows changed: {manifest_path}/{key}")
    return path, frame


def _append_stability_anchors(
    master: pd.DataFrame,
    spec: dict,
    candidates: pd.DataFrame,
    stability: pd.DataFrame,
    execution_audit: pd.DataFrame,
) -> pd.DataFrame:
    """Materialize explicitly preregistered migration anchors absent from master v1."""
    additions = []
    existing = set(zip(master["candidate_id"].astype(str), master["selection_role"].astype(str)))
    for entry in spec["candidate_contract"]["frozen_entries"]:
        identity = (str(entry["candidate_id"]), str(entry["selection_role"]))
        source_id = str(entry.get("source_challenger_id") or "")
        structure_key = str(entry.get("source_structure_key") or "")
        if identity in existing or not source_id or not structure_key:
            continue
        candidate_rows = candidates.loc[candidates["challenger_id"].astype(str).eq(source_id)]
        stability_rows = stability.loc[stability["structure_key"].astype(str).eq(structure_key)]
        audit_rows = execution_audit.loc[
            execution_audit["challenger_id"].astype(str).eq(source_id)
            & execution_audit["structure_key"].astype(str).eq(structure_key)
        ]
        if len(candidate_rows) != 1 or len(stability_rows) != 1 or len(audit_rows) != 1:
            raise ValueError(f"stability anchor source is not unique: {identity}")
        candidate = candidate_rows.iloc[0]
        stable = stability_rows.iloc[0]
        audit = audit_rows.iloc[0]
        if not bool(audit["execution_eligible"]):
            raise ValueError(f"stability anchor is not execution eligible: {identity}")
        additions.append({
            "candidate_id": identity[0],
            "action_scope": str(entry["action_scope"]),
            "selection_role": identity[1],
            "holding_count": int(candidate["holding_count"]),
            "candidate_tickers": candidate["tickers"],
            "candidate_weights": candidate["weights"],
            "absolute_return_p50": candidate["return_p50"],
            "absolute_return_p10": candidate["return_p10"],
            "absolute_max_drawdown_p50": candidate["max_drawdown_p50"],
            "absolute_max_drawdown_p90": candidate["max_drawdown_p90"],
            "paired_return_p50": stable["worst_paired_return_p50"],
            "paired_return_p10": stable["worst_paired_return_p10"],
            "paired_drawdown_cost_p50": stable["worst_paired_drawdown_cost_p50"],
            "paired_drawdown_cost_p90": stable["worst_paired_drawdown_cost_p90"],
            "target_012922_distance": stable["median_target_012922_distance"],
            "turnover": stable["turnover"],
            "current_transaction_cost": candidate["transaction_cost"],
            "current_effective_n": candidate["effective_n"],
            "current_weight_top1": candidate["weight_top1"],
            "current_weight_top3": candidate["weight_top3"],
            "whole_lot_shares": audit["whole_lot_shares"],
            "execution_status": spec["candidate_contract"]["active_execution_status"],
            "execution_constraint_failures": audit["execution_constraint_failures"],
            "execution_invested_usd": audit["execution_invested_usd"],
            "execution_residual_cash_usd": audit["execution_residual_cash_usd"],
            "execution_deployment_ratio": audit["execution_deployment_ratio"],
            "execution_risky_weight_l1_drift": "",
            "execution_risky_weight_max_abs_drift": "",
            "execution_actual_top1_weight": audit["execution_actual_top1_weight"],
            "execution_actual_top3_weight": audit["execution_actual_top3_weight"],
            "execution_actual_effective_n": audit["execution_actual_effective_n"],
            "execution_actual_risk_chain_top1_weight": audit["execution_actual_risk_chain_top1_weight"],
            "risk_chain_weights": "",
            "evidence_status": "REUSED_THREE_START_STABILITY_AND_WHOLE_LOT_AUDIT_ONLY",
            "portfolio_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
            "safe_leg_included": False,
            "external_index_included": False,
            "promotion_allowed": False,
        })
    if not additions:
        return master
    return pd.concat([master, pd.DataFrame(additions)], ignore_index=True, sort=False)


def run(args: argparse.Namespace) -> dict:
    spec_path = _resolve(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    validate_forward_spec(spec)
    registry_lineage = _validated_registry_lineage(spec)
    master_manifest_path = _resolve(args.master_manifest)
    master_manifest = json.loads(master_manifest_path.read_text(encoding="utf-8"))
    if master_manifest.get("manifest_type") != "ndx_pure_equity_challenger_master_table":
        raise ValueError("unexpected challenger master manifest")
    if master_manifest.get("promotion_allowed") is not False or master_manifest.get("fresh_oos_consumed") is not False:
        raise ValueError("challenger master governance changed")
    artifact = (master_manifest.get("artifacts") or {}).get("master") or {}
    master_path = Path(str(artifact.get("path") or ""))
    if not master_path.is_absolute() or file_sha256(master_path) != artifact.get("sha256"):
        raise ValueError("challenger master artifact mismatch")
    master = pd.read_csv(master_path, low_memory=False)
    if len(master) != int(artifact.get("rows") or -1):
        raise ValueError("challenger master row count changed")
    local_manifest_path = _resolve(args.local_execution_manifest)
    local_positions_path, local_positions = _manifest_artifact(
        local_manifest_path, "ndx_local_action_whole_lot_execution_audit", "positions",
    )
    fallback_manifest_path = _resolve(args.local_execution_frontier_manifest)
    fallback_positions_path, fallback_positions = _manifest_artifact(
        fallback_manifest_path, "ndx_local_execution_aware_training_frontiers", "positions",
    )
    execution_audit_path, execution_audit = _manifest_artifact(
        fallback_manifest_path, "ndx_local_execution_aware_training_frontiers", "audit",
    )
    training_manifest_path = _resolve(args.local_training_manifest)
    training_candidates_path, training_candidates = _manifest_artifact(
        training_manifest_path, "ndx_local_challenger_training_search", "candidates",
    )
    stability_manifest_path = _resolve(args.stability_manifest)
    stability_path, stability = _manifest_artifact(
        stability_manifest_path, "ndx_local_challenger_cross_start_training_stability", "stability",
    )
    master = _append_stability_anchors(
        master, spec, training_candidates, stability, execution_audit,
    )
    active, controls = build_forward_registry(master, spec)
    dynamic_manifest_path = _resolve(args.dynamic_manifest)
    dynamic_holdings_path, dynamic_holdings = _manifest_artifact(
        dynamic_manifest_path, "ndx_cardinality_pure_equity_aggressive_shortlist", "holdings",
    )
    incumbent_manifest_path = _resolve(args.incumbent_attribution_manifest)
    incumbent_projection_path, incumbent_projection = _manifest_artifact(
        incumbent_manifest_path, "ndx_incumbent_pit_execution_attribution", "projection",
    )
    risk_rows = []
    for entry in active.to_dict("records"):
        candidate_id = str(entry["candidate_id"])
        role = str(entry["selection_role"])
        if str(entry["action_scope"]) == "VARIABLE_CARDINALITY":
            source = dynamic_holdings.loc[
                dynamic_holdings["candidate_id"].astype(str).eq(candidate_id)
                & dynamic_holdings["selection_roles"].astype(str).eq(role)
            ][["ticker", "issuer_id", "risk_chain"]].copy()
            source_role = "DYNAMIC_SHORTLIST_HOLDINGS"
        elif role.endswith("_EXECUTION_FALLBACK"):
            base_role = role.removesuffix("_EXECUTION_FALLBACK")
            source = fallback_positions.loc[
                fallback_positions["candidate_id"].astype(str).eq(candidate_id)
                & fallback_positions["selection_role"].astype(str).eq(base_role)
                & fallback_positions["selection_status"].astype(str).eq("EXECUTION_COMPLIANT_FALLBACK")
            ][["ticker", "issuer_id", "risk_chain"]].copy()
            source_role = "LOCAL_EXECUTION_FALLBACK_POSITIONS"
        else:
            source = local_positions.loc[
                local_positions["candidate_id"].astype(str).eq(candidate_id)
                & local_positions["selection_role"].astype(str).eq(role)
            ][["ticker", "issuer_id", "risk_chain"]].copy()
            source_role = "LOCAL_METRIC_FIRST_POSITIONS"
            if source.empty and role.startswith("STABILITY_"):
                taxonomy = pd.concat([
                    fallback_positions[["ticker", "issuer_id", "risk_chain"]],
                    dynamic_holdings[["ticker", "issuer_id", "risk_chain"]],
                    incumbent_projection[["ticker", "issuer_id", "risk_chain"]],
                ], ignore_index=True).drop_duplicates()
                expected_tickers = {ticker for ticker in str(entry["candidate_tickers"]).split(";") if ticker}
                source = taxonomy.loc[taxonomy["ticker"].astype(str).isin(expected_tickers)].copy()
                if source["ticker"].astype(str).duplicated().any():
                    raise ValueError(f"stability anchor taxonomy is ambiguous: {entry['registry_entry_id']}")
                source_role = "STABILITY_ANCHOR_TAXONOMY_LOOKUP"
        expected = {ticker for ticker in str(entry["candidate_tickers"]).split(";") if ticker}
        if set(source["ticker"].astype(str)) != expected or len(source) != len(expected):
            raise ValueError(f"forward registry risk-chain coverage mismatch: {entry['registry_entry_id']}")
        for row in source.to_dict("records"):
            risk_rows.append({
                "registry_entry_id": entry["registry_entry_id"], "candidate_id": candidate_id,
                "selection_role": role, "ticker": row["ticker"], "issuer_id": row["issuer_id"],
                "risk_chain": row["risk_chain"], "mapping_source_role": source_role,
                "taxonomy_role": "FROZEN_AT_REGISTRATION_EXECUTION_CONSTRAINT_ONLY",
            })
    risk_map = pd.DataFrame(risk_rows).sort_values(
        ["registry_entry_id", "ticker"], kind="stable",
    ).reset_index(drop=True)

    state_path = _resolve(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    caps = {ticker: float(state["symbols"][ticker]["cap_total"]) for ticker in INCUMBENT}
    total = sum(caps.values())
    latest_attribution_date = incumbent_projection["selection_date"].astype(str).max()
    incumbent_mapping = incumbent_projection.loc[
        incumbent_projection["selection_date"].astype(str).eq(latest_attribution_date),
        ["ticker", "issuer_id", "risk_chain"],
    ].copy()
    if (
        set(incumbent_mapping["ticker"].astype(str)) != set(INCUMBENT)
        or len(incumbent_mapping) != len(INCUMBENT)
        or incumbent_mapping[["issuer_id", "risk_chain"]].astype(str).eq("").any().any()
    ):
        raise ValueError("incumbent forward attribution is incomplete or duplicated")
    incumbent_mapping = incumbent_mapping.set_index("ticker")
    baseline = pd.DataFrame([{
        "ticker": ticker, "cap_total_usd": caps[ticker], "frozen_weight": caps[ticker] / total,
        "issuer_id": incumbent_mapping.loc[ticker, "issuer_id"],
        "risk_chain": incumbent_mapping.loc[ticker, "risk_chain"],
        "risk_chain_mapping_selection_date": latest_attribution_date,
        "baseline_role": "SAME_DATE_ORIGINAL_8_CONTROL", "personal_off_strategy_position_included": False,
    } for ticker in INCUMBENT])

    output = _resolve(args.output_dir)
    immutable_targets = [
        output / "manifest.json",
        output / "active_forward_registry.csv",
        output / "non_active_forward_controls.csv",
        output / "original_8_forward_baseline.csv",
        output / "frozen_candidate_risk_chain_map.csv",
    ]
    if any(path.exists() for path in immutable_targets):
        raise ValueError(f"immutable forward registry output already exists: {output}")
    output.mkdir(parents=True, exist_ok=True)
    active_path = output / "active_forward_registry.csv"
    controls_path = output / "non_active_forward_controls.csv"
    baseline_path = output / "original_8_forward_baseline.csv"
    risk_map_path = output / "frozen_candidate_risk_chain_map.csv"
    _atomic_csv(active, active_path); _atomic_csv(controls, controls_path); _atomic_csv(baseline, baseline_path)
    _atomic_csv(risk_map, risk_map_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_pure_equity_challenger_forward_registry",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "PRE_REGISTERED_FORWARD_ONLY_NOT_ADMISSION",
        "registry_id": str(spec["registry_id"]),
        "registration_date": str(spec["registration_date"]),
        "execution_capital_contract": {
            key: (
                [str(value) for value in spec["forward_contract"][key]]
                if key == "capital_feasibility_observation_dates"
                else spec["forward_contract"][key]
            )
            for key in (
                "standardized_execution_cash_usd", "standardized_execution_cash_role",
                "standardized_execution_cash_derivation", "capital_feasibility_observation_dates",
                "capital_feasibility_uses_return_data", "cohort_version_reset_required",
                "minimum_cash_buffer_usd", "transaction_cost_bps",
            )
            if key in spec["forward_contract"]
        },
        "active_candidate_count": len(active),
        "failed_execution_control_count": int(controls["registry_status"].eq("FAILED_EXECUTION_CONTROL").sum()),
        "not_selected_control_count": int(controls["registry_status"].eq("FROZEN_NOT_SELECTED_CONTROL").sum()),
        "fresh_oos_cohorts": 0,
        "first_fresh_observation_on_or_after": str(
            spec["forward_contract"]["first_fresh_observation_on_or_after"]
        ),
        "active_candidate_counts_by_research_track": {
            str(key): int(value)
            for key, value in active.groupby("research_track").size().to_dict().items()
        },
        "promotion_policy_gate": dict(spec["promotion_contract"]["policy_gate"]),
        "registry_lineage": registry_lineage,
        "historical_return_data_read": False,
        "registration_date_or_later_price_data_read": False,
        "historical_whole_lot_shares_reused_for_future": False,
        "portfolio_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
        "safe_leg_included": False, "external_index_included": False,
        "personal_off_strategy_positions_included": False,
        "promotion_allowed": False, "live_config_changed": False,
        "state_changed": False, "today_advice_changed": False,
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "master_manifest": {"path": master_manifest_path.as_posix(), "sha256": file_sha256(master_manifest_path)},
            "master": {"path": master_path.as_posix(), "sha256": file_sha256(master_path)},
            "state": {"path": state_path.as_posix(), "sha256": file_sha256(state_path)},
            "local_execution_manifest": {"path": local_manifest_path.as_posix(), "sha256": file_sha256(local_manifest_path)},
            "local_execution_positions": {"path": local_positions_path.as_posix(), "sha256": file_sha256(local_positions_path)},
            "local_execution_frontier_manifest": {"path": fallback_manifest_path.as_posix(), "sha256": file_sha256(fallback_manifest_path)},
            "local_execution_fallback_positions": {"path": fallback_positions_path.as_posix(), "sha256": file_sha256(fallback_positions_path)},
            "local_execution_audit": {"path": execution_audit_path.as_posix(), "sha256": file_sha256(execution_audit_path)},
            "local_training_manifest": {"path": training_manifest_path.as_posix(), "sha256": file_sha256(training_manifest_path)},
            "local_training_candidates": {"path": training_candidates_path.as_posix(), "sha256": file_sha256(training_candidates_path)},
            "stability_manifest": {"path": stability_manifest_path.as_posix(), "sha256": file_sha256(stability_manifest_path)},
            "stability": {"path": stability_path.as_posix(), "sha256": file_sha256(stability_path)},
            "dynamic_manifest": {"path": dynamic_manifest_path.as_posix(), "sha256": file_sha256(dynamic_manifest_path)},
            "dynamic_holdings": {"path": dynamic_holdings_path.as_posix(), "sha256": file_sha256(dynamic_holdings_path)},
            "incumbent_attribution_manifest": {"path": incumbent_manifest_path.as_posix(), "sha256": file_sha256(incumbent_manifest_path)},
            "incumbent_attribution_projection": {"path": incumbent_projection_path.as_posix(), "sha256": file_sha256(incumbent_projection_path)},
        },
        "artifacts": {
            "active_registry": {"path": active_path.as_posix(), "rows": len(active), "sha256": file_sha256(active_path)},
            "non_active_controls": {"path": controls_path.as_posix(), "rows": len(controls), "sha256": file_sha256(controls_path)},
            "baseline": {"path": baseline_path.as_posix(), "rows": len(baseline), "sha256": file_sha256(baseline_path)},
            "risk_chain_map": {"path": risk_map_path.as_posix(), "rows": len(risk_map), "sha256": file_sha256(risk_map_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纯美股 challenger 未来前向注册表")
    parser.add_argument("--spec", default="config/ndx_challenger_forward_v3.yaml")
    parser.add_argument("--master-manifest", default="data/cache/research/ndx_challenger_master_table_v1/manifest.json")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--local-execution-manifest", default="data/cache/research/ndx_local_action_execution_v1/manifest.json")
    parser.add_argument("--local-execution-frontier-manifest", default="data/cache/research/ndx_local_execution_frontier_v1/manifest.json")
    parser.add_argument("--local-training-manifest", default="data/cache/research/ndx_local_challenger_training_v1/manifest.json")
    parser.add_argument("--stability-manifest", default="data/cache/research/ndx_local_challenger_stability_v1/manifest.json")
    parser.add_argument("--dynamic-manifest", default="data/cache/research/ndx_cardinality_aggressive_shortlist_v1/manifest.json")
    parser.add_argument("--incumbent-attribution-manifest", default="data/cache/research/ndx_incumbent_pit_attribution_v1/manifest.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_challenger_forward_registry_v3")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"challenger 前向注册失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"challenger 前向注册完成 | active={payload['active_candidate_count']} | "
        f"failed_execution={payload['failed_execution_control_count']} | "
        f"not_selected={payload['not_selected_control_count']} | fresh_oos=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
