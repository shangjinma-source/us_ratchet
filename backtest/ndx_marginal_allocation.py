"""Pre-register and audit incumbent-first marginal allocation research.

This module deliberately does not run a backtest. It defines the action
space that the next point-in-time engine must evaluate and provides the
deterministic allocation math used by that engine. The distinction matters:
the v8 experiments tested wholesale risk-sleeve replacement, while this
contract keeps existing holdings and assigns only future contributions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import yaml


class NdxMarginalAllocationError(ValueError):
    """Raised when a marginal-allocation contract is unsafe or inconsistent."""


PLAN_SCHEMA_VERSION = 1
ALLOWED_WHOLE_PORTFOLIO_COUNTS = (6, 8, 10, 12)
FORBIDDEN_GRID_KEYS = {
    "top_ns",
    "weight_modes",
    "max_weights",
    "sweep",
    "grid",
    "parameter_grid",
    "ordinary_topn_grid",
}

PLAN_COLUMN_LABELS = {
    "action_id": "动作编号",
    "stage": "研究阶段",
    "action_mode": "动作模式",
    "enabled": "当前是否可执行",
    "candidate_role": "候选角色",
    "candidate_ticker": "候选股票",
    "old_holding_sell_allowed": "是否允许卖出旧仓",
    "old_holding_count": "旧仓数量",
    "projected_holding_count": "预计持仓数量",
    "new_money_share": "新增资金候选比例",
    "incumbent_new_money_share": "新增资金旧仓比例",
    "current_top1": "当前Top1",
    "current_top3": "当前Top3",
    "current_effective_n": "当前有效持仓数",
    "reason": "说明",
}


def file_sha256(path: str | Path) -> str:
    """Return the content hash of a local evidence file."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ticker_list(value: Iterable[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.replace(",", ";").split(";")
    else:
        values = list(value)
    result = [str(item).strip().upper() for item in values if str(item).strip()]
    if len(result) != len(set(result)):
        raise NdxMarginalAllocationError("ticker list contains duplicates")
    return result


def _finite_number(value: Any, *, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxMarginalAllocationError(f"{name} must be numeric") from exc
    if not math.isfinite(parsed):
        raise NdxMarginalAllocationError(f"{name} must be finite")
    return parsed


def normalize_weights(
    weights: Mapping[str, Any],
    *,
    name: str,
    tolerance: float = 1e-9,
) -> dict[str, float]:
    """Normalize a positive ticker-weight map without hiding invalid input."""

    if not isinstance(weights, Mapping) or not weights:
        raise NdxMarginalAllocationError(f"{name} must be a non-empty mapping")
    result = {}
    for ticker, value in weights.items():
        symbol = str(ticker).strip().upper()
        if not symbol:
            raise NdxMarginalAllocationError(f"{name} contains an empty ticker")
        if symbol == "QQQ":
            raise NdxMarginalAllocationError("QQQ can never be a candidate")
        parsed = _finite_number(value, name=f"{name}.{symbol}")
        if parsed <= 0:
            raise NdxMarginalAllocationError(f"{name}.{symbol} must be positive")
        result[symbol] = parsed
    total = float(sum(result.values()))
    if not math.isclose(total, 1.0, abs_tol=tolerance, rel_tol=0.0):
        raise NdxMarginalAllocationError(
            f"{name} must sum to one; observed {total:.12f}"
        )
    return {ticker: value / total for ticker, value in result.items()}


def portfolio_shape(weights: Mapping[str, Any]) -> dict[str, Any]:
    """Compute concentration descriptors from a normalized portfolio map."""

    normalized = normalize_weights(weights, name="portfolio_weights")
    values = np.asarray(sorted(normalized.values(), reverse=True), dtype=float)
    return {
        "holding_count": int(len(values)),
        "top1": float(values[0]),
        "top3": float(values[:3].sum()),
        "effective_n": float(1.0 / np.dot(values, values)),
    }


def current_incumbent_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    """Read the current eight-name baseline without touching live state."""

    symbols = config.get("symbols") or []
    if not isinstance(symbols, list) or not symbols:
        raise NdxMarginalAllocationError("config.symbols is empty")
    caps = {}
    for item in symbols:
        if not isinstance(item, Mapping):
            raise NdxMarginalAllocationError("every config symbol must be a mapping")
        ticker = str(item.get("ticker") or "").strip().upper()
        cap = _finite_number(item.get("cap_total"), name=f"cap_total.{ticker}")
        if not ticker or ticker == "QQQ" or cap <= 0:
            raise NdxMarginalAllocationError(
                "current holdings contain an invalid ticker or cap"
            )
        if ticker in caps:
            raise NdxMarginalAllocationError(f"duplicate current holding: {ticker}")
        caps[ticker] = cap
    total = float(sum(caps.values()))
    weights = {ticker: cap / total for ticker, cap in caps.items()}
    safe_leg = config.get("safe_leg") or {}
    safe_ticker = str(safe_leg.get("ticker") or "SGOV").strip().upper()
    safe_weight = _finite_number(
        safe_leg.get("target_weight", 0.0), name="safe_leg.target_weight"
    )
    if not 0.0 <= safe_weight < 1.0:
        raise NdxMarginalAllocationError("safe-leg target weight must be in [0, 1)")
    return {
        "tickers": list(caps),
        "cap_total": caps,
        "weights": weights,
        "safe_ticker": safe_ticker,
        "safe_weight": safe_weight,
        **portfolio_shape(weights),
    }


def allocate_new_money(
    contribution: float,
    incumbent_weights: Mapping[str, Any],
    *,
    candidate_share: float,
    candidate_weights: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Allocate one contribution while preserving all existing positions.

    ``candidate_share`` is a share of this new contribution, never a share of
    the existing portfolio. No negative allocation is produced and no
    existing holding is sold. The candidate map may contain an incumbent
    ticker when the correct action is to add to an existing name; a genuinely
    new component is visible from the resulting ticker set.
    """

    amount = _finite_number(contribution, name="contribution")
    if amount < 0:
        raise NdxMarginalAllocationError("contribution must be non-negative")
    share = _finite_number(candidate_share, name="candidate_share")
    if not 0.0 <= share <= 1.0:
        raise NdxMarginalAllocationError("candidate_share must be in [0, 1]")
    incumbent = normalize_weights(incumbent_weights, name="incumbent_weights")
    candidate = {}
    if share > 0:
        candidate = normalize_weights(
            candidate_weights or {}, name="candidate_weights"
        )
    rows = []
    for ticker, weight in incumbent.items():
        rows.append({
            "ticker": ticker,
            "role": "incumbent",
            "allocation": amount * (1.0 - share) * weight,
            "new_money_share": (1.0 - share) * weight,
            "existing_holding_sell_notional": 0.0,
        })
    for ticker, weight in candidate.items():
        rows.append({
            "ticker": ticker,
            "role": "candidate" if ticker not in incumbent else "incumbent_addition",
            "allocation": amount * share * weight,
            "new_money_share": share * weight,
            "existing_holding_sell_notional": 0.0,
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=[
            "ticker",
            "role",
            "allocation",
            "new_money_share",
            "existing_holding_sell_notional",
        ])
    if not math.isclose(
        float(frame["allocation"].sum()), amount, abs_tol=1e-8, rel_tol=0.0
    ):
        raise NdxMarginalAllocationError(
            "new-money allocations do not sum to contribution"
        )
    if float(frame["existing_holding_sell_notional"].sum()) != 0.0:
        raise NdxMarginalAllocationError(
            "marginal allocation attempted to sell an old holding"
        )
    return frame.sort_values(["role", "ticker"], kind="stable").reset_index(drop=True)


def _find_forbidden_grid_keys(value: Any, *, path: str = "plan") -> list[str]:
    found = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_GRID_KEYS:
                found.append(f"{path}.{key_text}")
            found.extend(_find_forbidden_grid_keys(nested, path=f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_find_forbidden_grid_keys(nested, path=f"{path}[{index}]"))
    return found


def validate_plan(
    plan: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a narrow incumbent-first contract and return its audit."""

    if not isinstance(plan, Mapping):
        raise NdxMarginalAllocationError("plan root must be a mapping")
    errors: list[str] = []
    warnings: list[str] = []
    if int(plan.get("schema_version") or 0) != PLAN_SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if plan.get("research_only") is not True:
        errors.append("research_only must be true")
    if plan.get("qqq_role") != "benchmark_only_not_candidate":
        errors.append("qqq_role must keep QQQ out of candidates")
    objective = plan.get("objective_contract") or {}
    if objective.get("primary_target") != "012922":
        errors.append("primary_target must be 012922")
    if objective.get("qqq_performance_role") != "auxiliary_reference_only":
        errors.append("QQQ must be auxiliary only")
    if plan.get("live_config_mutation_allowed") is not False:
        errors.append("live_config_mutation_allowed must be false")
    if plan.get("today_advice_impact") != "none":
        errors.append("today_advice_impact must be none")
    forbidden = _find_forbidden_grid_keys(plan)
    if forbidden:
        errors.append("ordinary parameter grids are forbidden: " + ", ".join(forbidden))

    incumbent = plan.get("incumbent") or {}
    try:
        snapshot = current_incumbent_snapshot(config)
    except NdxMarginalAllocationError as exc:
        errors.append(str(exc))
        snapshot = None
    if snapshot is not None:
        declared_tickers = _ticker_list(incumbent.get("tickers"))
        if declared_tickers != snapshot["tickers"]:
            errors.append(
                "plan incumbent tickers do not match config.yaml: "
                f"declared={declared_tickers}, config={snapshot['tickers']}"
            )
        if incumbent.get("sell_existing_positions") is not False:
            errors.append("sell_existing_positions must be false in stage 1")
        if int(incumbent.get("holding_count") or 0) != snapshot["holding_count"]:
            errors.append("declared incumbent holding_count does not match config.yaml")
        if str(incumbent.get("safe_ticker") or "").upper() != snapshot["safe_ticker"]:
            errors.append("declared safe ticker does not match config.yaml")
        try:
            declared_safe = _finite_number(
                incumbent.get("safe_weight"), name="incumbent.safe_weight"
            )
        except NdxMarginalAllocationError as exc:
            errors.append(str(exc))
            declared_safe = None
        if declared_safe is not None and not math.isclose(
            declared_safe, snapshot["safe_weight"], abs_tol=1e-9, rel_tol=0.0
        ):
            errors.append("declared safe-leg weight does not match config.yaml")

    stage_one = plan.get("stage_1_marginal") or {}
    if stage_one.get("action_mode") != "new_money_only_no_sale":
        errors.append("stage_1_marginal.action_mode is not new_money_only_no_sale")
    if stage_one.get("old_holding_policy") != "freeze_existing_and_redirect_future_money":
        errors.append("stage 1 must freeze existing holdings")
    shares = stage_one.get("candidate_share_of_new_money")
    if not isinstance(shares, list) or not shares:
        errors.append("stage 1 candidate_share_of_new_money must be a list")
        shares = []
    parsed_shares = []
    for value in shares:
        try:
            parsed = _finite_number(value, name="candidate_share_of_new_money")
        except NdxMarginalAllocationError as exc:
            errors.append(str(exc))
            continue
        if not 0.0 <= parsed <= 0.20:
            errors.append(
                "candidate share must stay within the pre-registered 0%-20% bound"
            )
        parsed_shares.append(parsed)
    if parsed_shares != sorted(set(parsed_shares)):
        errors.append("candidate shares must be unique and ascending")
    if parsed_shares and not math.isclose(parsed_shares[0], 0.0, abs_tol=1e-12):
        errors.append("stage 1 must include the all-incumbent 0% control")
    if int(stage_one.get("max_new_candidate_slots") or 0) != 1:
        errors.append("stage 1 may add at most one candidate slot per review")
    if int(stage_one.get("review_interval_months") or 0) not in {6, 12}:
        errors.append("stage 1 review interval must be six or twelve months")
    selection = stage_one.get("candidate_selection") or {}
    if selection.get("ranking") != "price_then_quality_within_risk_chain":
        errors.append("stage 1 ranking must be price then quality within risk chain")
    if selection.get("valuation") != "overpay_penalty_only":
        errors.append("stage 1 valuation must be overpay penalty only")
    if selection.get("taxonomy_role") != "risk_construction_evidence_only":
        errors.append("taxonomy cannot directly increase a stock score")
    if selection.get("historical_label_backfill") is not False:
        errors.append("historical taxonomy backfill must be false")
    taxonomy_gate = selection.get("taxonomy_gate") or {}
    if taxonomy_gate.get("accepted_only_for_risk_chain") is not True:
        errors.append("risk-chain construction requires accepted taxonomy evidence")
    if taxonomy_gate.get("unclassified_policy") != "reject_and_report":
        errors.append("unclassified candidates must be rejected and reported")
    if taxonomy_gate.get("conflict_policy") != "reject_and_report":
        errors.append("taxonomy conflicts must be rejected and reported")

    stage_two = plan.get("stage_2_whole_sleeve") or {}
    counts = stage_two.get("holding_counts")
    if counts != [6, 8, 10, 12]:
        errors.append(
            "stage 2 holding_counts must be exactly [6, 8, 10, 12] and is not a broad topN grid"
        )
    if stage_two.get("enabled") is not False:
        errors.append("stage 2 must remain disabled until stage 1 evidence exists")
    if stage_two.get("allocation_solver") != "shrinkage_covariance_risk_budget":
        errors.append("stage 2 must use shrinkage covariance risk budgeting")
    if set(stage_two.get("simple_baselines") or []) != {"equal_weight", "source_weight"}:
        errors.append("stage 2 must retain equal-weight and source-weight baselines")
    constraints = stage_two.get("constraints") or {}
    for key in (
        "top3_not_above_incumbent",
        "effective_n_not_below_incumbent",
        "risk_chain_top1_reported",
        "turnover_and_cost_reported",
        "liquidity_gate_reported",
    ):
        if constraints.get(key) is not True:
            errors.append(f"stage 2 constraint is missing: {key}")

    prerequisites = plan.get("prerequisites") or {}
    if prerequisites.get("taxonomy_v2_current_incumbents") != "all_eight_plus_tsm_overlay":
        errors.append(
            "taxonomy prerequisite must cover all eight incumbents plus TSM overlay"
        )
    if not str(prerequisites.get("incumbent_taxonomy_overlay_manifest") or "").strip():
        errors.append("incumbent taxonomy overlay manifest is required")
    if prerequisites.get("exact_ndx_event_timing") is not True:
        warnings.append(
            "exact NDX event timing is not complete; execution must remain plan-only"
        )
    if prerequisites.get("event_gap_scope_locked") is not True:
        errors.append("known NDX event gaps must have an explicit locked scope")
    if not str(prerequisites.get("event_gap_disposition_manifest") or "").strip():
        errors.append("event-gap disposition manifest is required")
    if prerequisites.get("fresh_oos_required") is not True:
        errors.append("fresh OOS must be required")

    if errors:
        raise NdxMarginalAllocationError("; ".join(errors))
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "passed": True,
        "warnings": warnings,
        "incumbent": snapshot,
        "candidate_share_of_new_money": parsed_shares,
        "stage_2_holding_counts": list(ALLOWED_WHOLE_PORTFOLIO_COUNTS),
        "ordinary_grid_scan_rejected": True,
        "old_holding_sale_allowed": False,
    }


def load_plan(
    path: str | Path,
    *,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Load and hash-lock a YAML plan after fail-closed validation."""

    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise NdxMarginalAllocationError(f"cannot read marginal plan: {exc}") from exc
    audit = validate_plan(raw, config=config)
    normalized = copy.deepcopy(raw)
    normalized["_spec_path"] = str(source.resolve())
    normalized["_spec_sha256"] = _json_hash(raw)
    normalized["_config_snapshot"] = audit["incumbent"]
    normalized["_audit"] = audit
    return normalized


def build_plan_rows(plan: Mapping[str, Any], *, config: Mapping[str, Any]) -> pd.DataFrame:
    """Expand the declared action set into a human-readable plan table."""

    audit = validate_plan(plan, config=config)
    snapshot = audit["incumbent"]
    rows = []
    shares = audit["candidate_share_of_new_money"]
    for share in shares:
        is_control = math.isclose(float(share), 0.0, abs_tol=1e-12)
        rows.append({
            "action_id": (
                "stage1_incumbent_control"
                if is_control
                else f"stage1_marginal_{int(round(share * 100)):02d}pct"
            ),
            "stage": "stage_1_marginal",
            "action_mode": (
                "all_new_money_to_incumbents"
                if is_control
                else "new_money_only_no_sale"
            ),
            "enabled": True,
            "candidate_role": (
                "none" if is_control else "one_slot_same_chain_or_diversifier"
            ),
            "candidate_ticker": "" if is_control else "TBD_AFTER_POINT_IN_TIME_RANKING",
            "old_holding_sell_allowed": False,
            "old_holding_count": snapshot["holding_count"],
            "projected_holding_count": (
                snapshot["holding_count"]
                if is_control
                else snapshot["holding_count"] + 1
            ),
            "new_money_share": float(share),
            "incumbent_new_money_share": float(1.0 - share),
            "current_top1": snapshot["top1"],
            "current_top3": snapshot["top3"],
            "current_effective_n": snapshot["effective_n"],
            "reason": (
                "控制组：新增资金按当前8只cap比例投入"
                if is_control
                else "只允许新增资金进入一个点时候选；旧仓冻结，不生成卖出动作"
            ),
        })
    for count in audit["stage_2_holding_counts"]:
        rows.append({
            "action_id": f"stage2_whole_sleeve_count_{count}",
            "stage": "stage_2_whole_sleeve",
            "action_mode": "whole_sleeve_construction",
            "enabled": False,
            "candidate_role": "risk_chain_budgeted_portfolio",
            "candidate_ticker": "TBD_AFTER_STAGE1",
            "old_holding_sell_allowed": True,
            "old_holding_count": snapshot["holding_count"],
            "projected_holding_count": int(count),
            "new_money_share": np.nan,
            "incumbent_new_money_share": np.nan,
            "current_top1": snapshot["top1"],
            "current_top3": snapshot["top3"],
            "current_effective_n": snapshot["effective_n"],
            "reason": "只有阶段1边际证据稳定且完成精确成分事件后才可执行",
        })
    return pd.DataFrame(rows, columns=list(PLAN_COLUMN_LABELS))


def local_manifest_entry(path: str | Path, *, rows: int | None = None) -> dict[str, Any]:
    """Describe a derived artifact with a content hash."""

    target = Path(path)
    return {
        "filename": target.name,
        "rows": rows,
        "sha256": file_sha256(target),
    }
