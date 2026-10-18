"""Fail-closed P5 new-money transition preregistration.

This module validates readiness only.  It never writes live configuration, state,
broker snapshots, advice, or orders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from backtest.ndx_dynamic_shadow_p4_evidence import (
    PASS_STATUS,
    verify_p4_evaluation_evidence,
)


class NdxDynamicShadowTransitionError(RuntimeError):
    """Raised when the P5 transition boundary is weakened or unverifiable."""


def load_transition_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NdxDynamicShadowTransitionError("transition contract must be a mapping")
    gate = payload.get("p4_gate") or {}
    policy = payload.get("transition_policy") or {}
    approval = payload.get("approval_gate") or {}
    boundary = payload.get("evidence_boundary") or {}
    if (
        payload.get("schema_version") != 1
        or payload.get("transition_id") != "ndx_dynamic_shadow_transition_v1"
        or payload.get("research_track") != "portfolio_optimization"
        or payload.get("migration_control_included") is not False
        or gate.get("required_admission_status") != PASS_STATUS
        or str(gate.get("canonical_manifest"))
        != "data/cache/research/ndx_challenger_forward_v5/latest_evaluation/manifest.json"
        or int(gate.get("minimum_fresh_cohorts") or 0) != 12
        or int(gate.get("minimum_mature_cohorts") or 0) != 12
        or int(gate.get("minimum_distinct_regimes") or 0) != 2
        or gate.get("portfolio_optimization_only") is not True
        or gate.get("user_preference_is_reference_not_override") is not True
        or gate.get("target_012922_componentwise_gate_required") is not True
        or gate.get("original_8_componentwise_gate_required") is not True
        or policy.get("funding_source") != "FUTURE_NEW_MONEY_ONLY"
        or policy.get("sell_existing_positions_allowed") is not False
        or policy.get("whole_share_required") is not True
        or float(policy.get("transaction_cost_bps") or 0) != 10.0
        or float(policy.get("minimum_cash_buffer_usd") or 0) != 100.0
        or policy.get("fixed_holding_count") is not None
        or policy.get("dynamic_k_preserved") is not True
        or any(policy.get(key) is not False for key in (
            "automatic_order_creation_allowed", "automatic_live_config_mutation_allowed",
            "automatic_state_mutation_allowed", "automatic_broker_snapshot_mutation_allowed",
            "automatic_today_advice_mutation_allowed",
        ))
        or any(approval.get(key) is not True for key in (
            "today_diff_required", "rollback_snapshot_required", "explicit_user_approval_required",
        ))
        or approval.get("apply_supported_by_this_module") is not False
        or any(boundary.get(key) is not False for key in (
            "historical_training_result_may_unlock_p5", "early_shadow_result_may_unlock_p5",
            "not_yet_due_result_may_unlock_p5", "promotion_allowed", "live_mutation_allowed",
        ))
    ):
        raise NdxDynamicShadowTransitionError("P5 transition safety contract changed")
    return payload


def assess_transition_readiness(
    contract: Mapping[str, Any], *, repository_root: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    gate = contract["p4_gate"]
    expected = (root / str(gate["canonical_manifest"])).resolve()
    blockers: list[str] = [
        "CANONICAL_TODAY_DIFF_EVIDENCE_NOT_AVAILABLE",
        "CANONICAL_ROLLBACK_SNAPSHOT_EVIDENCE_NOT_AVAILABLE",
        "ONE_TIME_USER_APPROVAL_EVIDENCE_NOT_AVAILABLE",
    ]
    p4_evidence = None
    if not expected.is_file():
        blockers.append("P4_CANONICAL_V5_EVALUATION_NOT_AVAILABLE")
    else:
        try:
            p4_evidence = verify_p4_evaluation_evidence(
                expected, repository_root=root,
            )
        except Exception as exc:
            raise NdxDynamicShadowTransitionError(
                f"canonical P4 evidence rebuild failed: {type(exc).__name__}: {exc}"
            ) from exc
        if p4_evidence.get("raw_economic_path_replay_verified") is not True:
            blockers.append(str(
                p4_evidence.get("admission_blocker")
                or "RAW_ECONOMIC_REPLAY_NOT_VERIFIED"
            ))
        if not p4_evidence["eligible_portfolio_optimization_candidate_ids"]:
            blockers.append("P4_PORTFOLIO_OPTIMIZATION_GATE_NOT_VERIFIED")
    eligible_candidate_ids = (
        [] if p4_evidence is None
        else p4_evidence["eligible_portfolio_optimization_candidate_ids"]
    )
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_transition_readiness",
        "status": "READY_FOR_SEPARATE_APPROVED_APPLY_TOOL" if not blockers else "BLOCKED",
        "blockers": blockers,
        "p4_manifest_path": expected.as_posix(),
        "p4_manifest_sha256": (
            None if p4_evidence is None else p4_evidence["latest_manifest"]["sha256"]
        ),
        "p4_rebuilt_evidence": p4_evidence,
        "eligible_portfolio_optimization_candidate_ids": eligible_candidate_ids,
        "caller_supplied_summary_booleans_trusted": False,
        "caller_supplied_approval_booleans_accepted": False,
        "migration_control_included": False,
        "user_preference_override_allowed": False,
        "new_money_only": True,
        "sell_existing_positions_allowed": False,
        "apply_supported_by_this_module": False,
        "orders_created": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


__all__ = ["NdxDynamicShadowTransitionError", "assess_transition_readiness", "load_transition_contract"]
