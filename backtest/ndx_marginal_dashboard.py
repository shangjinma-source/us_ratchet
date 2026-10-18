"""Hash-verified read model for the v11 marginal-allocation dashboard."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.versioning import file_sha256


class NdxMarginalDashboardError(ValueError):
    pass


def _manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise NdxMarginalDashboardError(f"manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _verified_artifact(
    root: Path,
    manifest: dict[str, Any],
    artifact_key: str,
    filename: str,
) -> pd.DataFrame:
    artifact = (manifest.get("artifacts") or {}).get(artifact_key) or {}
    path = root / filename
    if not path.exists() or artifact.get("sha256") != file_sha256(path):
        raise NdxMarginalDashboardError(
            f"artifact hash mismatch: {artifact_key} ({path})"
        )
    frame = pd.read_csv(path, low_memory=False)
    expected_rows = artifact.get("rows")
    if expected_rows is not None and int(expected_rows) != len(frame):
        raise NdxMarginalDashboardError(f"artifact row count changed: {artifact_key}")
    return frame


def _clean_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.replace({np.nan: None})
    return clean.to_dict("records")


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def _incremental_exposure_rows(
    actions: pd.DataFrame,
    readiness: pd.DataFrame,
    incumbent_weights: dict[str, float],
    *,
    tsm_risk_chain: str,
    cost_bps: float,
) -> pd.DataFrame:
    chains = readiness.loc[
        readiness["role"].eq("incumbent_frozen"), ["ticker", "risk_chain"]
    ].set_index("ticker")["risk_chain"].astype(str).to_dict()
    chains["TSM"] = tsm_risk_chain
    rows = []
    for action in actions.to_dict("records"):
        share = float(action.get("target_candidate_share") or 0.0)
        chain_weights: dict[str, float] = {}
        issuer_weights = []
        for ticker, weight in incumbent_weights.items():
            amount = (1.0 - share) * float(weight)
            chain = str(chains.get(ticker) or "unclassified")
            chain_weights[chain] = chain_weights.get(chain, 0.0) + amount
            issuer_weights.append(amount)
        if str(action.get("ticker") or ""):
            chain = str(action.get("risk_chain") or "unclassified")
            chain_weights[chain] = chain_weights.get(chain, 0.0) + share
            issuer_weights.append(share)
        ordered = sorted(chain_weights.items(), key=lambda item: (-item[1], item[0]))
        rows.append({
            "action_id": action["action_id"],
            "ticker": action.get("ticker") or "",
            "risk_chain": action.get("risk_chain") or "",
            "target_candidate_share": share,
            "incremental_incumbent_share": 1.0 - share,
            "incremental_risk_chain_top1": ordered[0][1] if ordered else None,
            "incremental_risk_chain_top1_name": ordered[0][0] if ordered else None,
            "incremental_risk_chain_top3": sum(value for _, value in ordered[:3]),
            "incremental_effective_n": (
                1.0 / sum(value * value for value in issuer_weights)
                if issuer_weights else None
            ),
            "modeled_transaction_cost_bps": float(cost_bps),
            "modeled_cost_usd": None,
            "modeled_cost_usd_status": "REQUIRES_EXPLICIT_NEW_MONEY",
            "sell_old_holdings": False,
        })
    return pd.DataFrame(rows)


def read_verified_marginal_dashboard(
    *,
    stage1_dir: Path,
    forward_dir: Path,
    overlay_path: Path,
    event_gap_manifest_path: Path,
) -> dict[str, Any]:
    """Read current structure and frozen forward monitoring as separate layers."""
    stage_manifest = _manifest(stage1_dir / "manifest.json")
    forward_report = forward_dir / "latest_evaluation"
    forward_manifest = _manifest(forward_report / "manifest.json")
    if stage_manifest.get("candidate_admission_count") != 0:
        raise NdxMarginalDashboardError("stage-1 admission unexpectedly opened")
    if forward_manifest.get("candidate_admission_count") != 0:
        raise NdxMarginalDashboardError("forward admission unexpectedly opened")
    if stage_manifest.get("live_config_changed") is not False:
        raise NdxMarginalDashboardError("stage-1 live mutation identity changed")
    if forward_manifest.get("live_config_changed") is not False:
        raise NdxMarginalDashboardError("forward live mutation identity changed")

    event_manifest = _manifest(event_gap_manifest_path)
    if event_manifest.get("scope_lock_complete") is not True:
        raise NdxMarginalDashboardError("event-gap scope lock is incomplete")
    if event_manifest.get("historical_backtest_allowed") is not False:
        raise NdxMarginalDashboardError("event-gap historical guard unexpectedly opened")
    if event_manifest.get("v11_execution_allowed") is not False:
        raise NdxMarginalDashboardError("event-gap v11 execution guard unexpectedly opened")
    event_scope = _verified_artifact(
        event_gap_manifest_path.parent,
        event_manifest,
        "blocking_scope",
        "blocking_scope.csv",
    )

    readiness = _verified_artifact(
        stage1_dir, stage_manifest, "candidate_readiness", "candidate_readiness.csv"
    )
    actions = _verified_artifact(
        stage1_dir, stage_manifest, "allocation_actions", "allocation_actions.csv"
    )
    metrics = _verified_artifact(
        stage1_dir, stage_manifest, "metric_readiness", "metric_readiness.csv"
    )
    interim = _verified_artifact(
        forward_report, forward_manifest, "interim_snapshot", "interim_snapshot.csv"
    )
    curves = _verified_artifact(
        forward_report, forward_manifest, "curve_points", "curve_points.csv"
    )
    inputs = _verified_artifact(
        forward_report, forward_manifest, "inputs", "cohort_inputs.csv"
    )
    current = readiness.loc[_as_bool(readiness["component_shortlisted"])].copy()
    current = current.sort_values("shortlist_rank", kind="stable")
    if len(current) != 22 or current["risk_chain"].nunique() != 22:
        raise NdxMarginalDashboardError("current shortlist is not 22 unique risk chains")

    index_path = forward_dir / "cohort_index.jsonl"
    records = [
        json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise NdxMarginalDashboardError("no immutable forward cohort is registered")
    latest_record = records[-1]
    cohort_manifest_path = Path(latest_record["cohort_manifest_path"])
    cohort_path = cohort_manifest_path.parent / "cohort_actions.csv"
    if file_sha256(cohort_manifest_path) != latest_record["cohort_manifest_sha256"]:
        raise NdxMarginalDashboardError("immutable cohort manifest hash changed")
    if file_sha256(cohort_path) != latest_record["cohort_csv_sha256"]:
        raise NdxMarginalDashboardError("immutable cohort actions hash changed")
    cohort = pd.read_csv(cohort_path, low_memory=False, keep_default_na=False)
    incumbent_weights = json.loads(str(cohort.iloc[0]["incumbent_weights_json"]))

    overlay_version = (stage_manifest.get("input_versions") or {}).get(
        "incumbent_overlay"
    ) or {}
    if overlay_version.get("sha256") != file_sha256(overlay_path):
        raise NdxMarginalDashboardError("incumbent overlay hash changed")
    overlay = pd.read_csv(overlay_path, low_memory=False)
    tsm_rows = overlay.loc[overlay["ticker"].astype(str).eq("TSM")]
    if len(tsm_rows) != 1 or str(tsm_rows.iloc[0]["status"]) != "accepted":
        raise NdxMarginalDashboardError("TSM overlay risk chain is unavailable")
    cost_bps = float(forward_manifest.get("modeled_transaction_cost_bps") or 10.0)
    exposures = _incremental_exposure_rows(
        actions,
        readiness,
        incumbent_weights,
        tsm_risk_chain=str(tsm_rows.iloc[0]["risk_chain"]),
        cost_bps=cost_bps,
    )

    current_columns = [
        "shortlist_rank", "ticker", "name", "risk_chain", "strict_prior_price",
        "price_date", "attack_score", "quality_score", "valuation_score",
        "valuation_guarded_price_score", "valuation_guard_penalty_attack_equivalent",
        "taxonomy_confidence", "liquidity_status", "broker_tradability_status",
        "why_not_selected",
    ]
    interim_columns = [
        "observation_date", "action_id", "ticker", "risk_chain",
        "target_candidate_share", "available_common_sessions", "entry_date",
        "interim_exit_date", "display_return_delta_vs_incumbent",
        "display_dd_cost_vs_incumbent", "fresh_oos_eligible", "mature", "status",
        "evidence_role",
    ]
    interim = interim.sort_values(
        ["display_return_delta_vs_incumbent", "target_candidate_share", "ticker"],
        ascending=[False, False, True], na_position="last", kind="stable",
    )
    blockers = (
        current["why_not_selected"].fillna("").astype(str).str.split(";").explode()
    )
    blocker_summary = (
        blockers[blockers.ne("")].value_counts().rename_axis("blocker").reset_index(name="count")
    )
    return {
        "schema_version": 1,
        "available": True,
        "research_only": True,
        "candidate_admission_allowed": False,
        "stage_2_unlocked": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "event_evidence_gate": {
            "scope_lock_complete": True,
            "historical_backtest_allowed": False,
            "v11_execution_allowed": False,
            "partial_exact_addition_count": int(
                (event_manifest.get("summary") or {}).get(
                    "partial_exact_addition_count"
                ) or 0
            ),
            "unresolved_removal_date_count": int(
                (event_manifest.get("summary") or {}).get(
                    "unresolved_removal_date_count"
                ) or 0
            ),
            "cases": _clean_records(event_scope[[
                "ticker", "status", "blocked_selection_start",
                "blocked_selection_end", "exact_addition_supported",
                "exact_removal_date_supported", "evidence_status",
                "resolution_required",
            ]]),
        },
        "current_structure": {
            "status": stage_manifest.get("status"),
            "selection_date": str(current.iloc[0]["selection_date"]),
            "candidate_count": len(current),
            "action_count": len(actions),
            "new_money": stage_manifest.get("new_money"),
            "new_money_status": (
                "EXPLICIT" if stage_manifest.get("new_money") is not None
                else "NOT_PROVIDED_NO_USD_OR_SHARE_GUESS"
            ),
            "candidates": _clean_records(current[current_columns]),
            "actions": _clean_records(exposures),
            "metric_readiness": _clean_records(metrics),
            "blocker_summary": _clean_records(blocker_summary),
        },
        "frozen_forward": {
            "status": forward_manifest.get("status"),
            "cohort_observation_date": latest_record["observation_date"],
            "cohort_origin": latest_record["cohort_origin"],
            "cohort_fresh_oos_eligible": bool(latest_record["fresh_oos_eligible"]),
            "cohort_csv_sha256": latest_record["cohort_csv_sha256"],
            "registered_cohorts": int(forward_manifest.get("registered_cohorts") or 0),
            "fresh_primary_mature_windows": int(
                forward_manifest.get("fresh_primary_mature_windows_max_per_action") or 0
            ),
            "minimum_required_fresh_primary_windows": int(
                forward_manifest.get("minimum_required_fresh_primary_windows") or 0
            ),
            "modeled_transaction_cost_bps": cost_bps,
            "target_012922_version": forward_manifest.get("target_012922_version"),
            "cohort_inputs": _clean_records(inputs),
            "interim_actions": _clean_records(interim[interim_columns]),
            "curve_points": _clean_records(curves),
            "curve_evidence_role": "FORWARD_CURVE_MONITORING_ONLY_NOT_ADMISSION_EVIDENCE",
        },
    }
