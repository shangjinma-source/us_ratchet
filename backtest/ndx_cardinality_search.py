"""Contracts and complexity audit for variable-cardinality NDX research.

This module does not read returns or search for a winning portfolio.  It turns
the current hash-locked security evidence into two technology-preference
universes and measures the exact combinatorial space for every feasible
holding count.  A later discovery runner must consume this bundle rather than
silently reverting to fixed top-N portfolios.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml


class NdxCardinalitySearchError(ValueError):
    """Raised when the variable-cardinality research contract is unsafe."""


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_search_plan(path: str | Path) -> dict[str, Any]:
    try:
        plan = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise NdxCardinalitySearchError(f"cannot read search plan: {exc}") from exc
    validate_search_plan(plan)
    return plan


def validate_search_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if int(plan.get("schema_version") or 0) != 1:
        errors.append("schema_version must be 1")
    if plan.get("research_only") is not True:
        errors.append("plan must remain research_only")
    if plan.get("live_config_mutation_allowed") is not False:
        errors.append("live config mutation must be disabled")
    if plan.get("today_advice_impact") != "none":
        errors.append("today advice impact must remain none")
    if plan.get("return_data_read") is not False:
        errors.append("plan construction cannot read returns")

    objective = plan.get("objective_contract") or {}
    if objective.get("technology_preference") != "primary_universe_prior":
        errors.append("technology preference must define the primary universe")
    if objective.get("portfolio_scope") != "hsbc_us_equity_sleeve_only":
        errors.append("portfolio scope must remain the HSBC US equity sleeve only")
    if objective.get("safe_leg_role") != "excluded_from_optimization_and_comparison":
        errors.append("safe leg must remain outside stock-sleeve optimization and comparison")
    if objective.get("external_index_context") != "user_managed_outside_strategy_approximately_half_of_total_assets":
        errors.append("external index allocation must remain context, not a backtest component")
    if objective.get("incumbent_role") != "iteration_start_and_guard":
        errors.append("current eight must remain iteration start and guard")
    if objective.get("target_012922_role") != "core_return_drawdown_envelope":
        errors.append("012922 must remain the core return/drawdown envelope")
    if objective.get("qqq_role") != "auxiliary_reference_only_not_candidate":
        errors.append("QQQ must remain auxiliary and cannot be a candidate")
    if objective.get("holding_count_policy") != "dynamic_from_one_to_eligible_issuer_count":
        errors.append("holding count must be dynamic from one to eligible issuer count")
    required_frontiers = set(objective.get("required_frontiers") or [])
    expected_frontiers = {
        "return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90",
        "target_012922_distance", "multiobjective_pareto",
    }
    if required_frontiers != expected_frontiers:
        errors.append("required frontiers are incomplete")

    tracks = plan.get("universe_tracks") or {}
    strict = tracks.get("strict_technology") or {}
    adjacent = tracks.get("technology_plus_adjacent") or {}
    strict_chains = list(strict.get("accepted_risk_chains") or [])
    adjacent_chains = list(adjacent.get("additional_risk_chains") or [])
    if not strict_chains or len(strict_chains) != len(set(strict_chains)):
        errors.append("strict technology chains must be non-empty and unique")
    if set(strict_chains) & set(adjacent_chains):
        errors.append("adjacent chains must not duplicate strict technology chains")
    if adjacent.get("inherits") != "strict_technology":
        errors.append("adjacent sensitivity must inherit strict technology")

    gates = plan.get("evidence_gates") or {}
    if gates.get("taxonomy_status") != "accepted_only":
        errors.append("taxonomy evidence must fail closed")
    if gates.get("issuer_deduplication") != "one_security_per_issuer_per_portfolio":
        errors.append("one issuer per portfolio slot is required")
    if gates.get("qqq_candidate_allowed") is not False:
        errors.append("QQQ candidate access must be false")
    if gates.get("historical_label_backfill_allowed") is not False:
        errors.append("historical taxonomy backfill must be false")

    search = plan.get("search_contract") or {}
    if int(search.get("minimum_holding_count") or 0) != 1:
        errors.append("minimum holding count must be one")
    if search.get("maximum_holding_count") != "eligible_issuer_count":
        errors.append("maximum holding count must be derived from eligible issuers")
    if search.get("fixed_topn_ranking_forbidden") is not True:
        errors.append("fixed top-N ranking must be forbidden")
    if search.get("full_sample_max_sharpe_or_xirr_forbidden") is not True:
        errors.append("full-sample objective maximization must be forbidden")
    for key in (
        "search_coverage_audit_required", "theoretical_space_required",
        "pruned_space_required", "expanded_nodes_required", "unevaluated_space_required",
    ):
        if search.get(key) is not True:
            errors.append(f"{key} must be true")

    evaluation = plan.get("evaluation_contract") or {}
    if evaluation.get("historical_discovery_role") != "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION":
        errors.append("consumed history may only support training discovery")
    if evaluation.get("consumed_history_may_be_relabelled_fresh_oos") is not False:
        errors.append("consumed history cannot be relabelled fresh OOS")
    if evaluation.get("stage_1_fresh_evidence_required_for_promotion") is not True:
        errors.append("promotion must remain blocked pending stage-1 fresh evidence")

    if errors:
        raise NdxCardinalitySearchError("; ".join(errors))
    return {"passed": True, "plan_sha256": _json_hash(plan)}


def _overlay_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "security_id": str(row.get("security_id") or ""),
        "issuer_id": str(row.get("issuer_id") or ""),
        "ticker": str(row.get("ticker") or "").upper(),
        "name": str(row.get("ticker") or "").upper(),
        "role": "incumbent_overlay",
        "risk_chain": str(row.get("risk_chain") or "unclassified"),
        "taxonomy_status": str(row.get("status") or "unclassified"),
        "taxonomy_confidence": str(row.get("confidence") or ""),
        "evidence_available_date": str(row.get("evidence_available_date") or ""),
        "quality_input_ready": None,
        "liquidity_status": "INCUMBENT_OVERLAY_NOT_CURRENT_NDX",
        "broker_tradability_status": "UNVERIFIED",
    }


def build_search_universe(
    readiness: pd.DataFrame,
    overlay: pd.DataFrame,
    plan: Mapping[str, Any],
) -> pd.DataFrame:
    required = {
        "security_id", "issuer_id", "ticker", "name", "role", "risk_chain",
        "taxonomy_status", "taxonomy_confidence", "evidence_available_date",
        "quality_input_ready", "liquidity_status", "broker_tradability_status",
    }
    missing = sorted(required - set(readiness.columns))
    if missing:
        raise NdxCardinalitySearchError(f"candidate readiness columns missing: {missing}")
    if readiness["security_id"].duplicated().any():
        raise NdxCardinalitySearchError("candidate readiness security_id must be unique")
    frame = readiness[list(required)].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()

    incumbent_tickers = set(plan["objective_contract"]["incumbent_tickers"])
    missing_incumbents = incumbent_tickers - set(frame["ticker"])
    for ticker in sorted(missing_incumbents):
        matches = overlay.loc[overlay["ticker"].astype(str).str.upper().eq(ticker)]
        if len(matches) != 1:
            raise NdxCardinalitySearchError(
                f"missing incumbent {ticker} requires exactly one overlay row"
            )
        frame = pd.concat([frame, pd.DataFrame([_overlay_row(matches.iloc[0])])], ignore_index=True)

    if "QQQ" in set(frame["ticker"]):
        raise NdxCardinalitySearchError("QQQ cannot enter the security universe")
    if not incumbent_tickers.issubset(set(frame["ticker"])):
        raise NdxCardinalitySearchError("all current eight incumbents must remain visible")

    strict_chains = set(
        plan["universe_tracks"]["strict_technology"]["accepted_risk_chains"]
    )
    adjacent_chains = strict_chains | set(
        plan["universe_tracks"]["technology_plus_adjacent"]["additional_risk_chains"]
    )
    accepted = frame["taxonomy_status"].eq("accepted")
    frame["strict_technology_eligible"] = accepted & frame["risk_chain"].isin(strict_chains)
    frame["technology_plus_adjacent_eligible"] = accepted & frame["risk_chain"].isin(adjacent_chains)
    frame["incumbent"] = frame["ticker"].isin(incumbent_tickers)
    frame["exclusion_reason"] = frame.apply(
        lambda row: "" if row["technology_plus_adjacent_eligible"] else (
            "TAXONOMY_NOT_ACCEPTED" if row["taxonomy_status"] != "accepted"
            else "OUTSIDE_TECHNOLOGY_PREFERENCE_TRACKS"
        ), axis=1,
    )
    frame["selection_status"] = frame.apply(
        lambda row: "STRICT_TECHNOLOGY" if row["strict_technology_eligible"] else (
            "TECHNOLOGY_ADJACENT_SENSITIVITY"
            if row["technology_plus_adjacent_eligible"] else "EXCLUDED_AND_REPORTED"
        ), axis=1,
    )
    return frame.sort_values(
        ["selection_status", "risk_chain", "issuer_id", "ticker"], kind="stable"
    ).reset_index(drop=True)


def issuer_dedup_combination_counts(issuer_multiplicities: list[int]) -> list[int]:
    """Count k-security portfolios with at most one security from each issuer."""
    if any(int(value) <= 0 for value in issuer_multiplicities):
        raise NdxCardinalitySearchError("issuer multiplicities must be positive")
    dp = [1]
    for multiplicity in issuer_multiplicities:
        nxt = dp + [0]
        for k in range(1, len(nxt)):
            nxt[k] += dp[k - 1] * int(multiplicity)
        dp = nxt
    return dp


def cardinality_space(
    universe: pd.DataFrame,
    *,
    track: str,
    exact_limit: int,
) -> pd.DataFrame:
    column = {
        "strict_technology": "strict_technology_eligible",
        "technology_plus_adjacent": "technology_plus_adjacent_eligible",
    }.get(track)
    if column is None:
        raise NdxCardinalitySearchError(f"unknown universe track: {track}")
    eligible = universe.loc[universe[column]].copy()
    if eligible.empty:
        raise NdxCardinalitySearchError(f"universe track is empty: {track}")
    multiplicities = eligible.groupby("issuer_id")["security_id"].size().astype(int).tolist()
    dedup = issuer_dedup_combination_counts(multiplicities)
    n_security = len(eligible)
    n_issuer = len(multiplicities)
    rows = []
    for k in range(1, n_issuer + 1):
        raw = math.comb(n_security, k) if k <= n_security else 0
        feasible = int(dedup[k])
        mode = "EXACT_ENUMERATION_ALLOWED" if feasible <= exact_limit else "BOUNDED_MULTIOBJECTIVE_SEARCH"
        rows.append({
            "universe_track": track,
            "holding_count": k,
            "eligible_security_count": n_security,
            "eligible_issuer_count": n_issuer,
            "raw_security_combinations": str(raw),
            "issuer_dedup_feasible_combinations": str(feasible),
            "issuer_dedup_pruned_combinations": str(raw - feasible),
            "planned_search_mode": mode,
            "historical_result_role": "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION",
            "promotion_allowed": False,
            "required_frontier_output": "RETURN;DRAWDOWN;BAD_TAIL;012922_DISTANCE;PARETO",
        })
    return pd.DataFrame(rows)


def search_family_rows(plan: Mapping[str, Any]) -> pd.DataFrame:
    descriptions = {
        "incumbent_control": "当前8只股票风险仓基线，不含SGOV，不假设其最优",
        "add_only": "保留旧仓，只增加新标或现有标的新增资金",
        "freeze_future_money": "旧仓不卖，但失格标的不再获得新增资金",
        "single_replacement": "训练发现用单股替换；实盘仍需today diff和确认",
        "bounded_double_replacement": "有限双股替换，禁止扩成无审计多元消融",
        "variable_cardinality_whole_sleeve": "从1只到合格issuer数的所有可行持仓基数",
    }
    return pd.DataFrame([
        {
            "search_family": family,
            "description": descriptions[family],
            "development_allowed": True,
            "historical_discovery_allowed": True,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
        }
        for family in plan["search_families"]
    ])


def metric_contract_rows(plan: Mapping[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "metric": metric,
            "value": None,
            "status": "NOT_AVAILABLE_IN_PLAN_ONLY",
            "required_result_layer": ";".join(plan["evaluation_contract"]["result_layers"]),
            "reason": "本工具不读取收益；后续训练发现运行器计算，但不得冒充fresh OOS",
        }
        for metric in plan["evaluation_contract"]["metrics"]
    ])
