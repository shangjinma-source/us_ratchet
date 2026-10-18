"""Deterministic analysis of completed NDX experiment-lab evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.ndx_competition import _issuer_key
from core.helpers import atomic_write_text
from data.ndx_history import get_ndx_point_in_time_history


SHAPE_KEYS = [
    "lookback_years",
    "top_n",
    "weight_mode",
    "rebalance_months",
    "safe_weight",
    "max_weight",
    "trade_cost_bps",
]
FAMILY_KEYS = [
    "top_n",
    "weight_mode",
    "rebalance_months",
    "safe_weight",
    "max_weight",
]
CORE_METRICS = [
    "target_excess_p50",
    "target_excess_p10",
    "target_dd_relief_p50",
    "target_dd_relief_p10",
    "turnover_x_p50",
]
PROFILE_CANDIDATE_EFFECT_METRICS = CORE_METRICS + [
    "incumbent_xirr_p50_margin",
    "incumbent_xirr_p10_margin",
    "incumbent_dd_relief_p50",
    "incumbent_dd_relief_p90",
    "max_sic4_weight_p90",
    "max_sic2_weight_p90",
]
PROFILE_WINDOW_EFFECT_METRICS = [
    "strategy_xirr",
    "strategy_maxdd",
    "target_excess_xirr",
    "target_dd_relief",
    "incumbent_xirr_margin",
    "incumbent_dd_relief",
    "turnover_x",
    "max_sic4_weight_p90",
    "max_sic2_weight_p90",
]
LOWER_IS_BETTER_METRICS = {
    "strategy_maxdd",
    "turnover_x",
    "turnover_x_p50",
    "max_sic4_weight_p90",
    "max_sic2_weight_p90",
}
CONCENTRATION_GUARD_TOLERANCE = 1e-8


def _active_shape_keys(frame: pd.DataFrame) -> list[str]:
    if "profile_id" in frame and frame["profile_id"].notna().any():
        return ["profile_id", "lookback_years", "trade_cost_bps"]
    return list(SHAPE_KEYS)


def _active_family_keys(frame: pd.DataFrame) -> list[str]:
    if "profile_id" in frame and frame["profile_id"].notna().any():
        return ["profile_id"]
    return list(FAMILY_KEYS)


class NdxExperimentAnalysisError(ValueError):
    """Raised when a lab bundle is incomplete or unsafe to compare."""


def _summary_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_verified_bundle(
    output_dir: Path,
    *,
    strategy_config_path: str | Path | None = None,
) -> tuple[dict, dict[str, pd.DataFrame]]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise NdxExperimentAnalysisError(f"manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("completed_jobs") != manifest.get("planned_jobs"):
        raise NdxExperimentAnalysisError("experiment jobs are incomplete")
    if int(manifest.get("failed_jobs") or 0) != 0:
        raise NdxExperimentAnalysisError("experiment contains failed jobs")
    if (manifest.get("selection_constraint_audit") or {}).get("passed") is not True:
        raise NdxExperimentAnalysisError("selection constraint audit did not pass")
    versions = manifest.get("phase_version_consistency") or {}
    if not versions or any(not value.get("comparison_ready") for value in versions.values()):
        raise NdxExperimentAnalysisError("input versions are inconsistent within a phase")

    expected_config_hash = manifest.get("strategy_config_sha256")
    config_path = strategy_config_path or manifest.get("strategy_config_path")
    if expected_config_hash:
        if not config_path or not Path(config_path).exists():
            raise NdxExperimentAnalysisError("strategy config used by the experiment is missing")
        if _content_hash(Path(config_path)) != expected_config_hash:
            raise NdxExperimentAnalysisError("strategy config hash no longer matches the experiment")

    files = {
        "candidates": "candidates.csv",
        "windows": "windows.csv",
        "selections": "selections.csv",
        "gate_failures": "gate_failures.csv",
        "versions": "versions.csv",
    }
    evidence_files = manifest.get("evidence_files") or {}
    frames = {}
    for key, filename in files.items():
        path = output_dir / filename
        if not path.exists():
            raise NdxExperimentAnalysisError(f"required evidence missing: {path}")
        evidence = evidence_files.get(key) or {}
        if evidence.get("filename") != filename or not evidence.get("sha256"):
            raise NdxExperimentAnalysisError(f"evidence fingerprint missing: {filename}")
        if _content_hash(path) != evidence["sha256"]:
            raise NdxExperimentAnalysisError(f"evidence fingerprint mismatch: {filename}")
        frames[key] = pd.read_csv(
            path,
            dtype={"target_benchmark": str} if key == "candidates" else None,
            low_memory=False,
        )
        if len(frames[key]) != int(evidence.get("rows", -1)):
            raise NdxExperimentAnalysisError(f"evidence row count mismatch: {filename}")
    if frames["candidates"].empty or frames["windows"].empty or frames["selections"].empty:
        raise NdxExperimentAnalysisError("core evidence tables must not be empty")
    expected_rows = {
        "candidates": manifest.get("candidate_rows"),
        "windows": manifest.get("window_rows"),
        "selections": manifest.get("selection_rows"),
    }
    for key, expected in expected_rows.items():
        if expected is None or len(frames[key]) != int(expected):
            raise NdxExperimentAnalysisError(
                "core evidence row counts do not match the manifest"
            )
    objective_contract = manifest.get("objective_contract") or {}
    if objective_contract:
        evidence_targets = set(
            frames["candidates"]["target_benchmark"].dropna().astype(str).str.upper()
        )
        expected_target = str(objective_contract.get("primary_target") or "").upper()
        if evidence_targets != {expected_target}:
            raise NdxExperimentAnalysisError(
                "candidate evidence violates the primary optimization target"
            )
    return manifest, frames


def _parameter_effects(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    parameters = [
        "lookback_years",
        "top_n",
        "weight_mode",
        "rebalance_months",
        "safe_weight",
        "max_weight",
        "trade_cost_bps",
    ]
    parameters.extend(
        key for key in (
            "profile_id",
            "selection_mode",
            "correlation_threshold",
            "cluster_max_weight",
            "defense_mode",
            "defense_signal",
            "target_vol",
            "defense_vol_window",
            "defense_drawdown_lookback_days",
            "defense_drawdown_trigger",
            "defense_release_step",
            "fundamental_score_weight",
            "quality_policy_id",
            "quality_selection_mode",
            "quality_challenge_pool_size",
            "max_quality_replacements",
            "max_names_per_sic4",
            "max_names_per_sic2",
            "sic4_max_weight",
            "sic2_max_weight",
        )
        if key in candidates and candidates[key].notna().any()
    )
    for parameter in parameters:
        for value, frame in candidates.groupby(parameter, dropna=False):
            rows.append({
                "parameter": parameter,
                "value": value,
                "rows": len(frame),
                "median_target_excess_p50": frame["target_excess_p50"].median(),
                "best_target_excess_p50": frame["target_excess_p50"].max(),
                "best_target_excess_p10": frame["target_excess_p10"].max(),
                "median_target_dd_relief_p50": frame["target_dd_relief_p50"].median(),
                "best_target_dd_relief_p50": frame["target_dd_relief_p50"].max(),
                "median_turnover_x": frame["turnover_x_p50"].median(),
            })
    return pd.DataFrame(rows)


def _profile_effect_rows(
    baseline: pd.DataFrame,
    alternative: pd.DataFrame,
    *,
    index: list[str],
    metrics: list[str],
    baseline_id: str,
    alternative_id: str,
    evidence_level: str,
) -> list[dict]:
    available_metrics = [
        metric
        for metric in metrics
        if metric in baseline.columns and metric in alternative.columns
    ]
    if not available_metrics:
        return []
    paired = baseline[index + available_metrics].merge(
        alternative[index + available_metrics],
        on=index,
        suffixes=("_baseline", "_alternative"),
        validate="one_to_one",
    )
    rows = []
    for metric in available_metrics:
        left = pd.to_numeric(paired[f"{metric}_baseline"], errors="coerce")
        right = pd.to_numeric(paired[f"{metric}_alternative"], errors="coerce")
        delta = (right - left).dropna()
        lower_is_better = metric in LOWER_IS_BETTER_METRICS
        rows.append({
            "evidence_level": evidence_level,
            "parameter": "profile_id",
            "baseline": baseline_id,
            "alternative": alternative_id,
            "metric": metric,
            "preferred_direction": "lower" if lower_is_better else "higher",
            "pairs": len(delta),
            "delta_p10": delta.quantile(0.10),
            "delta_p50": delta.median(),
            "delta_p90": delta.quantile(0.90),
            "positive_rate": float((delta > 0).mean()) if len(delta) else np.nan,
            "improvement_rate": (
                float((delta < 0).mean())
                if lower_is_better and len(delta)
                else float((delta > 0).mean()) if len(delta) else np.nan
            ),
        })
    return rows


def _paired_effects(
    candidates: pd.DataFrame,
    windows: pd.DataFrame | None = None,
    *,
    baseline_id: str | None = None,
) -> pd.DataFrame:
    if "profile_id" in candidates and candidates["profile_id"].notna().any():
        available_ids = set(candidates["profile_id"].dropna().astype(str))
        if baseline_id is None and "seed_rank_w0" in available_ids:
            baseline_id = "seed_rank_w0"
        if not baseline_id:
            return pd.DataFrame()
        if baseline_id not in available_ids:
            raise NdxExperimentAnalysisError(
                f"declared analysis baseline is absent: {baseline_id}"
            )
        baseline = candidates[candidates["profile_id"].eq(baseline_id)]
        rows = []
        for profile_id, alternative in candidates.groupby("profile_id", dropna=False):
            if profile_id == baseline_id:
                continue
            candidate_index = [
                key for key in ("phase_id", "job_id")
                if key in candidates.columns
            ] or ["lookback_years", "trade_cost_bps"]
            rows.extend(_profile_effect_rows(
                baseline,
                alternative,
                index=candidate_index,
                metrics=PROFILE_CANDIDATE_EFFECT_METRICS,
                baseline_id=str(baseline_id),
                alternative_id=str(profile_id),
                evidence_level="cost_rollup",
            ))
            if windows is None or windows.empty or "profile_id" not in windows:
                continue
            baseline_windows = windows[windows["profile_id"].eq(baseline_id)]
            alternative_windows = windows[windows["profile_id"].eq(profile_id)]
            window_index = [
                key for key in ("phase_id", "job_id", "start", "end")
                if key in windows.columns
            ]
            if baseline_windows.empty or alternative_windows.empty or not window_index:
                continue
            rows.extend(_profile_effect_rows(
                baseline_windows,
                alternative_windows,
                index=window_index,
                metrics=PROFILE_WINDOW_EFFECT_METRICS,
                baseline_id=str(baseline_id),
                alternative_id=str(profile_id),
                evidence_level="paired_window",
            ))
        return pd.DataFrame(rows)

    comparisons = [
        ("safe_weight", 0.0, 0.14),
        ("safe_weight", 0.0, 0.26),
        ("rebalance_months", 12, 6),
        ("rebalance_months", 6, 3),
        ("top_n", 8, 10),
        ("top_n", 10, 12),
        ("max_weight", 0.25, 0.35),
        ("lookback_years", 1.0, 2.0),
        ("lookback_years", 3.0, 2.0),
        ("trade_cost_bps", 5.0, 25.0),
        ("weight_mode", "equal", "source_weight"),
        ("weight_mode", "inverse_vol", "source_weight"),
        ("weight_mode", "risk_parity", "source_weight"),
        ("weight_mode", "score_risk", "source_weight"),
    ]
    rows = []
    for parameter, baseline, alternative in comparisons:
        index = [key for key in SHAPE_KEYS if key != parameter]
        subset = candidates[candidates[parameter].isin([baseline, alternative])]
        pivot = subset.pivot_table(
            index=index,
            columns=parameter,
            values=CORE_METRICS,
            aggfunc="first",
        )
        for metric in CORE_METRICS:
            if (metric, baseline) not in pivot or (metric, alternative) not in pivot:
                continue
            delta = (pivot[(metric, alternative)] - pivot[(metric, baseline)]).dropna()
            rows.append({
                "parameter": parameter,
                "baseline": baseline,
                "alternative": alternative,
                "metric": metric,
                "pairs": len(delta),
                "delta_p10": delta.quantile(0.10),
                "delta_p50": delta.median(),
                "delta_p90": delta.quantile(0.90),
                "positive_rate": float((delta > 0).mean()),
            })
    return pd.DataFrame(rows)


def _robust_families(candidates: pd.DataFrame) -> pd.DataFrame:
    family_keys = _active_family_keys(candidates)
    return candidates.groupby(family_keys).agg(
        observations=("shape_id", "size"),
        p50_worst=("target_excess_p50", "min"),
        p50_median=("target_excess_p50", "median"),
        p50_best=("target_excess_p50", "max"),
        p10_worst=("target_excess_p10", "min"),
        p10_median=("target_excess_p10", "median"),
        dd_p50_worst=("target_dd_relief_p50", "min"),
        dd_p50_median=("target_dd_relief_p50", "median"),
        win_rate_best=("target_win_rate", "max"),
        turnover_median=("turnover_x_p50", "median"),
    ).reset_index().sort_values(
        ["p50_worst", "p10_worst", "dd_p50_worst"], ascending=False
    )


def _window_stress(windows: pd.DataFrame) -> pd.DataFrame:
    shape_keys = _active_shape_keys(windows)
    return windows.groupby(shape_keys).agg(
        windows=("start", "size"),
        win_rate=("target_excess_xirr", lambda value: float((value > 0).mean())),
        target_excess_min=("target_excess_xirr", "min"),
        target_excess_p10=("target_excess_xirr", lambda value: value.quantile(0.10)),
        target_excess_p50=("target_excess_xirr", "median"),
        target_excess_max=("target_excess_xirr", "max"),
        target_dd_relief_p10=("target_dd_relief", lambda value: value.quantile(0.10)),
        target_dd_relief_p50=("target_dd_relief", "median"),
        incumbent_margin_p10=("incumbent_xirr_margin", lambda value: value.quantile(0.10)),
        incumbent_margin_p50=("incumbent_xirr_margin", "median"),
    ).reset_index()


def _selection_concentration(
    selections: pd.DataFrame,
    *,
    canonical_cost_bps: float,
    shape_keys: list[str] | None = None,
    incumbent_weights: dict[str, float] | None = None,
    incumbent_safe_weight: float = 0.0,
) -> pd.DataFrame:
    shape_keys = list(shape_keys or _active_shape_keys(selections))
    source = selections[np.isclose(selections["trade_cost_bps"], canonical_cost_bps)].copy()
    event_keys = shape_keys + [
        "selection_date",
        "report_date",
        "available_date",
        "accession_number",
        "tickers",
        "weights",
    ]
    missing = [key for key in event_keys if key not in source]
    if missing:
        raise NdxExperimentAnalysisError(
            f"selection evidence is missing event identity columns: {missing}"
        )
    unique_events = source.drop_duplicates(event_keys)
    raw_groups = source.groupby(shape_keys, sort=False)
    rows = []
    for key, frame in unique_events.groupby(shape_keys, sort=False):
        raw_frame = raw_groups.get_group(key)
        effective_n = []
        top1 = []
        top3 = []
        for event in frame.itertuples(index=False):
            candidate_by_issuer: dict[str, float] = {}
            for item in str(event.weights).split(";"):
                if ":" not in item:
                    continue
                ticker, raw_weight = item.split(":", 1)
                issuer = _issuer_key(ticker)
                candidate_by_issuer[issuer] = (
                    candidate_by_issuer.get(issuer, 0.0) + float(raw_weight)
                )
            challenger_weight = float(
                getattr(event, "challenger_sleeve_weight", 1.0)
            )
            if not np.isfinite(challenger_weight):
                challenger_weight = 1.0
            combined = dict(candidate_by_issuer)
            if challenger_weight < 1.0 - 1e-12:
                if not incumbent_weights:
                    raise NdxExperimentAnalysisError(
                        "incumbent-anchored concentration lacks incumbent weights"
                    )
                candidate_safe_weight = float(getattr(event, "safe_weight", 0.0))
                candidate_risk = challenger_weight * (1.0 - candidate_safe_weight)
                incumbent_risk = (
                    (1.0 - challenger_weight) * (1.0 - incumbent_safe_weight)
                )
                total_risk = candidate_risk + incumbent_risk
                if total_risk <= 0:
                    raise NdxExperimentAnalysisError(
                        "incumbent-anchored concentration has no risk allocation"
                    )
                combined = {}
                for ticker, weight in incumbent_weights.items():
                    issuer = _issuer_key(ticker)
                    combined[issuer] = combined.get(issuer, 0.0) + (
                        incumbent_risk * float(weight) / total_risk
                    )
                for issuer, weight in candidate_by_issuer.items():
                    combined[issuer] = combined.get(issuer, 0.0) + (
                        candidate_risk * float(weight) / total_risk
                    )
            weights = sorted(combined.values(), reverse=True)
            effective_n.append(1.0 / sum(weight * weight for weight in weights))
            top1.append(weights[0])
            top3.append(sum(weights[:3]))
        rows.append({
            **dict(zip(shape_keys, key)),
            "selection_rows": len(frame),
            "window_conditioned_rows": len(raw_frame),
            "duplicate_window_rows": len(raw_frame) - len(frame),
            "effective_n_p10": float(np.quantile(effective_n, 0.10)),
            "effective_n_p50": float(np.median(effective_n)),
            "top1_p50": float(np.median(top1)),
            "top1_p90": float(np.quantile(top1, 0.90)),
            "top3_p50": float(np.median(top3)),
            "top3_p90": float(np.quantile(top3, 0.90)),
            "window_conditioned_churn_p50": raw_frame["churn"].median(),
        })
    return pd.DataFrame(rows)


def _concentration_baselines(cfg) -> tuple[pd.DataFrame, dict]:
    history, history_meta = get_ndx_point_in_time_history(cfg)
    if history.empty:
        raise NdxExperimentAnalysisError("NDX point-in-time history is empty")
    qqq_rows = []
    for (report_date, available_date), frame in history.groupby(
        ["report_date", "available_date"]
    ):
        by_issuer: dict[str, float] = {}
        for item in frame.itertuples(index=False):
            issuer = _issuer_key(item.ticker)
            by_issuer[issuer] = by_issuer.get(issuer, 0.0) + float(item.weight)
        weights = np.asarray(list(by_issuer.values()), dtype=float)
        weights /= float(weights.sum())
        ordered = np.sort(weights)[::-1]
        qqq_rows.append({
            "source": "qqq_sec_nport",
            "report_date": str(report_date)[:10],
            "available_date": str(available_date)[:10],
            "security_or_issuer_count": len(weights),
            "effective_n": 1.0 / float(weights @ weights),
            "top1": ordered[0],
            "top3": float(ordered[:3].sum()),
            "top10": float(ordered[:10].sum()),
        })

    incumbent = np.asarray([float(item.cap_total) for item in cfg.symbols], dtype=float)
    if incumbent.size == 0 or not np.isfinite(incumbent).all() or incumbent.sum() <= 0:
        raise NdxExperimentAnalysisError("incumbent concentration baseline is invalid")
    incumbent /= float(incumbent.sum())
    ordered = np.sort(incumbent)[::-1]
    incumbent_evidence = {
        "source": "current_config_risk_sleeve_targets",
        "security_or_issuer_count": len(incumbent),
        "effective_n": 1.0 / float(incumbent @ incumbent),
        "top1": float(ordered[0]),
        "top3": float(ordered[:3].sum()),
        "weights": {
            item.ticker: float(weight) for item, weight in zip(cfg.symbols, incumbent)
        },
        "history_version_id": history_meta.to_dict().get("version_id"),
    }
    qqq = pd.DataFrame(qqq_rows)
    qqq_summary = pd.DataFrame([
        {
            "source": "qqq_sec_nport_quantile",
            "quantile": quantile,
            "effective_n": qqq["effective_n"].quantile(quantile),
            "top1": qqq["top1"].quantile(quantile),
            "top3": qqq["top3"].quantile(quantile),
            "top10": qqq["top10"].quantile(quantile),
        }
        for quantile in (0.0, 0.1, 0.5, 0.9, 1.0)
    ])
    incumbent_row = {
        "source": incumbent_evidence["source"],
        "quantile": np.nan,
        "effective_n": incumbent_evidence["effective_n"],
        "top1": incumbent_evidence["top1"],
        "top3": incumbent_evidence["top3"],
        "top10": 1.0,
    }
    return pd.concat([qqq_summary, pd.DataFrame([incumbent_row])], ignore_index=True), incumbent_evidence


def _apply_concentration_guard(
    candidates: pd.DataFrame,
    concentration: pd.DataFrame,
    *,
    shape_keys: list[str],
    incumbent: dict,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    if concentration.empty:
        raise NdxExperimentAnalysisError("candidate concentration evidence is empty")
    merged = candidates.merge(
        concentration,
        on=shape_keys,
        validate="one_to_one",
    )
    merged["concentration_guard_passed"] = (
        (
            merged["effective_n_p10"]
            >= incumbent["effective_n"] - CONCENTRATION_GUARD_TOLERANCE
        )
        & (
            merged["top1_p90"]
            <= incumbent["top1"] + CONCENTRATION_GUARD_TOLERANCE
        )
        & (
            merged["top3_p90"]
            <= incumbent["top3"] + CONCENTRATION_GUARD_TOLERANCE
        )
    )
    merged["concentration_effective_n_margin"] = (
        merged["effective_n_p10"] - incumbent["effective_n"]
    )
    merged["concentration_top1_margin"] = (
        incumbent["top1"] - merged["top1_p90"]
    )
    merged["concentration_top3_margin"] = (
        incumbent["top3"] - merged["top3_p90"]
    )
    return merged


def _candidate_concentration_by_cost(
    candidates: pd.DataFrame,
    selections: pd.DataFrame,
    *,
    shape_keys: list[str],
    incumbent: dict,
    incumbent_safe_weight: float,
) -> pd.DataFrame:
    rows = []
    for cost in sorted(
        pd.to_numeric(candidates["trade_cost_bps"], errors="coerce").dropna().unique()
    ):
        cost_candidates = candidates[
            np.isclose(candidates["trade_cost_bps"], float(cost))
        ]
        concentration = _selection_concentration(
            selections,
            canonical_cost_bps=float(cost),
            shape_keys=shape_keys,
            incumbent_weights=incumbent["weights"],
            incumbent_safe_weight=incumbent_safe_weight,
        )
        rows.append(
            _apply_concentration_guard(
                cost_candidates,
                concentration,
                shape_keys=shape_keys,
                incumbent=incumbent,
            )
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _phase_decision(
    *,
    objective_compatible: bool,
    profile_experiment: bool,
    component_family: str | None,
    training_qualified: bool,
    locked_validation_executed: bool,
    locked_validation_passed: bool,
) -> tuple[str, str, list[str]]:
    if not objective_compatible:
        return (
            "SUPERSEDED_QQQ_AUXILIARY_DIAGNOSTIC_ONLY",
            "ACTIVE_ITERATION",
            ["restore the 012922 objective contract before further comparison"],
        )
    if locked_validation_executed:
        if locked_validation_passed:
            return (
                "LOCKED_VALIDATION_PASSED_REQUIRES_FINAL_REVIEW",
                "VALIDATION_PASSED_REVIEW_REQUIRED",
                [
                    "freeze the validated profile and complete today-diff and execution review",
                    "require explicit user confirmation before any live configuration change",
                ],
            )
        return (
            "LOCKED_VALIDATION_FAILED_NO_PROMOTION",
            "ACTIVE_ITERATION_VALIDATION_FAILED",
            [
                "freeze the tested profile as failed out-of-sample and do not tune it on the held-out period",
                "keep the incumbent configuration and today's advice unchanged",
                "develop a new point-in-time factor hypothesis and reserve new external validation evidence",
            ],
        )
    if training_qualified:
        return (
            "TRAINING_CANDIDATES_REQUIRE_LOCKED_VALIDATION",
            "ACTIVE_ITERATION",
            [
                "freeze exactly one training-qualified profile before validation",
                "keep live configuration unchanged until validation and final review pass",
            ],
        )
    if profile_experiment:
        decision = (
            "NO_QUALITY_SIC_PROMOTION"
            if component_family == "quality_sic"
            else "NO_PROFILE_COMPONENT_PROMOTION"
        )
        return (
            decision,
            "ACTIVE_ITERATION",
            [
                "compare declared profiles only within training evidence",
                "pre-register a new hypothesis instead of tuning failed shapes",
            ],
        )
    return (
        "NO_PRICE_ONLY_PROMOTION",
        "ACTIVE_ITERATION",
        [
            "continue point-in-time factor research",
            "keep live configuration unchanged",
        ],
    )


def _split_phase_evidence(
    candidates: pd.DataFrame,
    windows: pd.DataFrame,
    selections: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if "phase_role" in candidates:
        phase_roles = (
            candidates["phase_role"].fillna("").astype(str).str.strip().str.lower()
        )
        locked_mask = phase_roles.eq("locked_validation")
    else:
        locked_mask = pd.Series(False, index=candidates.index)
    locked_candidates = candidates.loc[locked_mask].copy()
    training_candidates = candidates.loc[~locked_mask].copy()
    locked_phase_ids = set(
        locked_candidates.get("phase_id", pd.Series(dtype=str)).astype(str)
    )

    def split_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not locked_phase_ids or "phase_id" not in frame:
            return frame.copy(), frame.iloc[0:0].copy()
        is_locked = frame["phase_id"].astype(str).isin(locked_phase_ids)
        return frame.loc[~is_locked].copy(), frame.loc[is_locked].copy()

    training_windows, locked_windows = split_rows(windows)
    training_selections, locked_selections = split_rows(selections)
    return (
        training_candidates,
        locked_candidates,
        training_windows,
        locked_windows,
        training_selections,
        locked_selections,
    )


def _research_seeds(candidates: pd.DataFrame, *, primary_target: str = "TARGET") -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    rows = []

    def add(role: str, frame: pd.DataFrame, reason: str) -> None:
        if frame.empty:
            return
        best = frame.sort_values(
            ["target_excess_p50", "target_excess_p10", "target_dd_relief_p50"],
            ascending=False,
        ).iloc[0].to_dict()
        rows.append({
            **best,
            "seed_role": role,
            "seed_status": "STRUCTURE_ONLY_NOT_VALIDATION",
            "locked_validation_eligible": False,
            "promotion_allowed": False,
            "reason": reason,
        })

    add(
        "closest_primary_target_return",
        candidates,
        f"Closest training return shape versus {primary_target}; not a validation result.",
    )
    add(
        "low_turnover_reference",
        candidates[candidates["turnover_x_p50"] <= 2.0],
        "Low-turnover structural reference; not a promotion candidate.",
    )
    add(
        "incumbent_concentration_compliant",
        candidates[candidates["concentration_guard_passed"]],
        "Best shape no more concentrated than the incumbent risk sleeve.",
    )
    add(
        "incumbent_concentration_compliant_low_turnover",
        candidates[
            candidates["concentration_guard_passed"]
            & (candidates["turnover_x_p50"] <= 2.0)
        ],
        "Low-turnover shape that also stays inside the incumbent concentration envelope.",
    )
    return pd.DataFrame(rows)


def analyze_ndx_experiment(
    output_dir: str | Path,
    cfg,
    *,
    canonical_cost_bps: float = 10.0,
    strategy_config_path: str | Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict]:
    root = Path(output_dir)
    manifest, evidence = _read_verified_bundle(
        root,
        strategy_config_path=strategy_config_path,
    )
    candidates = evidence["candidates"].copy()
    targets = sorted(set(candidates["target_benchmark"].dropna().astype(str).str.upper()))
    if len(targets) != 1:
        raise NdxExperimentAnalysisError(
            f"experiment must have exactly one primary target: {targets}"
        )
    primary_target = targets[0]
    objective_contract = manifest.get("objective_contract") or {}
    contracted_target = str(objective_contract.get("primary_target") or "").upper()
    if contracted_target and contracted_target != primary_target:
        raise NdxExperimentAnalysisError(
            "evidence target does not match the experiment objective contract"
        )

    (
        training_candidates,
        locked_candidates,
        training_windows,
        locked_windows,
        training_selections,
        locked_selections,
    ) = _split_phase_evidence(
        candidates,
        evidence["windows"],
        evidence["selections"],
    )
    if training_candidates.empty:
        raise NdxExperimentAnalysisError("experiment contains no training candidates")

    shape_keys = _active_shape_keys(training_candidates)
    profile_experiment = shape_keys[0] == "profile_id"
    analysis_contract = manifest.get("analysis_contract") or {}
    baseline_profile_id = (
        str(analysis_contract.get("baseline_profile_id") or "").strip() or None
    )
    component_family = (
        str(analysis_contract.get("component_family") or "").strip() or None
    )
    if profile_experiment and baseline_profile_id is None:
        profile_ids = set(training_candidates["profile_id"].dropna().astype(str))
        if "seed_rank_w0" in profile_ids:
            baseline_profile_id = "seed_rank_w0"
    baseline, incumbent = _concentration_baselines(cfg)
    incumbent_safe_weight = (
        float(cfg.safe_leg.target_weight) if cfg.safe_leg else 0.0
    )
    concentration_shape_keys = list(shape_keys)
    if "phase_id" in training_candidates and "phase_id" in training_selections:
        concentration_shape_keys.insert(0, "phase_id")
    concentration = _selection_concentration(
        training_selections,
        canonical_cost_bps=canonical_cost_bps,
        shape_keys=concentration_shape_keys,
        incumbent_weights=incumbent["weights"],
        incumbent_safe_weight=incumbent_safe_weight,
    )
    canonical = training_candidates[
        np.isclose(training_candidates["trade_cost_bps"], canonical_cost_bps)
    ]
    if canonical.empty or concentration.empty:
        raise NdxExperimentAnalysisError(
            f"canonical trade cost is absent from the evidence: {canonical_cost_bps:g} bps"
        )
    canonical = _apply_concentration_guard(
        canonical,
        concentration,
        shape_keys=concentration_shape_keys,
        incumbent=incumbent,
    )

    locked_validation_executed = not locked_candidates.empty
    locked_validation = pd.DataFrame()
    if locked_validation_executed:
        if locked_windows.empty or locked_selections.empty:
            raise NdxExperimentAnalysisError(
                "locked validation candidates lack window or selection evidence"
            )
        locked_shape_keys = _active_shape_keys(locked_candidates)
        if "phase_id" in locked_candidates and "phase_id" in locked_selections:
            locked_shape_keys.insert(0, "phase_id")
        locked_validation = _candidate_concentration_by_cost(
            locked_candidates,
            locked_selections,
            shape_keys=locked_shape_keys,
            incumbent=incumbent,
            incumbent_safe_weight=incumbent_safe_weight,
        )
        locked_validation["locked_validation_passed"] = (
            locked_validation["admission_passed"].fillna(False).astype(bool)
            & locked_validation["concentration_guard_passed"].fillna(False).astype(bool)
        )
        locked_validation = locked_validation.sort_values(
            ["phase_id", "profile_id", "trade_cost_bps"],
            kind="stable",
        ).reset_index(drop=True)

    seeds = _research_seeds(canonical, primary_target=primary_target)
    best = canonical.sort_values(
        ["target_excess_p50", "target_excess_p10"], ascending=False
    ).iloc[0]
    compliant = canonical[canonical["concentration_guard_passed"]].sort_values(
        ["target_excess_p50", "target_excess_p10"], ascending=False
    )
    best_compliant = compliant.iloc[0] if not compliant.empty else None
    admission_passed_rows = int(candidates["admission_passed"].sum())
    training_admission_passed_rows = int(training_candidates["admission_passed"].sum())
    training_qualified_rows = int(
        (
            canonical["admission_passed"].fillna(False).astype(bool)
            & canonical["concentration_guard_passed"].fillna(False).astype(bool)
        ).sum()
    )
    locked_validation_passed_rows = (
        int(locked_validation["locked_validation_passed"].sum())
        if locked_validation_executed else 0
    )
    locked_validation_passed = locked_validation_passed_rows > 0
    objective_compatible = bool(objective_contract) and primary_target != "QQQ"
    decision, direction_status, next_research = _phase_decision(
        objective_compatible=objective_compatible,
        profile_experiment=profile_experiment,
        component_family=component_family,
        training_qualified=training_qualified_rows > 0,
        locked_validation_executed=locked_validation_executed,
        locked_validation_passed=locked_validation_passed,
    )
    construction_keys = [
        key for key in (
            "top_n",
            "weight_mode",
            "rebalance_months",
            "safe_weight",
            "challenger_sleeve_weight",
            "max_weight",
            "selection_mode",
            "correlation_lookback_days",
            "correlation_threshold",
            "correlation_pool_size",
            "max_names_per_cluster",
            "cluster_max_weight",
            "fundamental_score_weight",
            "quality_policy_id",
            "max_names_per_sic4",
            "max_names_per_sic2",
            "sic4_max_weight",
            "sic2_max_weight",
            "defense_mode",
            "defense_signal",
            "target_vol",
            "defense_band",
            "defense_vol_window",
            "defense_exec_band",
            "defense_drawdown_lookback_days",
            "defense_drawdown_trigger",
            "defense_drawdown_full",
            "defense_max_safe_weight",
            "defense_release_step",
        )
        if key in canonical
    ]
    best_shape_keys = list(dict.fromkeys(
        (["phase_id"] if "phase_id" in canonical else [])
        + shape_keys
        + construction_keys
    ))
    result_metric_keys = [
        "phase_id",
        "profile_id",
        "challenger_sleeve_weight",
        "lookback_years",
        "top_n",
        "weight_mode",
        "rebalance_months",
        "trade_cost_bps",
        "windows",
        "target_win_rate",
        "target_excess_p50",
        "target_excess_p10",
        "target_dd_relief_p50",
        "target_dd_relief_p10",
        "incumbent_xirr_p50_margin",
        "incumbent_xirr_p10_margin",
        "incumbent_dd_relief_p50",
        "incumbent_dd_relief_p90",
        "target_return_passed",
        "target_risk_passed",
        "target_gate_passed",
        "incumbent_gate_passed",
        "admission_passed",
        "concentration_guard_passed",
        "locked_validation_passed",
        "effective_n_p10",
        "top1_p90",
        "top3_p90",
        "failed_checks",
    ]
    locked_results = []
    for _, row in locked_validation.iterrows():
        matching_windows = locked_windows[
            locked_windows["phase_id"].astype(str).eq(str(row["phase_id"]))
            & locked_windows["profile_id"].astype(str).eq(str(row["profile_id"]))
            & np.isclose(locked_windows["lookback_years"], float(row["lookback_years"]))
            & np.isclose(locked_windows["trade_cost_bps"], float(row["trade_cost_bps"]))
        ]
        result = {
            key: _summary_scalar(row[key])
            for key in result_metric_keys
            if key in row.index
        }
        result.update({
            "first_window_start": (
                str(matching_windows["start"].min())[:10]
                if not matching_windows.empty else None
            ),
            "last_window_start": (
                str(matching_windows["start"].max())[:10]
                if not matching_windows.empty else None
            ),
            "evaluation_end": (
                str(matching_windows["end"].max())[:10]
                if not matching_windows.empty else None
            ),
        })
        locked_results.append(result)
    summary = {
        "schema_version": 1,
        "analysis_id": f"{manifest.get('experiment_id')}_analysis",
        "source_experiment_id": manifest.get("experiment_id"),
        "objective_contract": objective_contract or None,
        "primary_target": primary_target,
        "qqq_performance_role": (
            objective_contract.get("qqq_performance_role")
            if objective_contract else "legacy_target_or_reference_unspecified"
        ),
        "objective_compatible": objective_compatible,
        "source_manifest_sha256": _content_hash(root / "manifest.json"),
        "engine_sha256": manifest.get("engine_sha256"),
        "evidence_sha256": {
            key: value.get("sha256")
            for key, value in (manifest.get("evidence_files") or {}).items()
        },
        "input_version_bundle_ids": {
            key: value.get("bundle_ids")
            for key, value in (manifest.get("phase_version_consistency") or {}).items()
        },
        "constraint_audit_passed": True,
        "candidate_rows": len(candidates),
        "training_candidate_rows": len(training_candidates),
        "locked_validation_candidate_rows": len(locked_candidates),
        "canonical_cost_bps": canonical_cost_bps,
        "canonical_candidate_rows": len(canonical),
        "profile_experiment": profile_experiment,
        "analysis_contract": analysis_contract or None,
        "baseline_profile_id": baseline_profile_id,
        "component_family": component_family,
        "shape_keys": shape_keys,
        "concentration_event_policy": (
            "unique point-in-time portfolio states; overlapping rolling-window duplicates removed"
        ),
        "admission_passed_rows": admission_passed_rows,
        "training_admission_passed_rows": training_admission_passed_rows,
        "training_qualified_rows": training_qualified_rows,
        "target_return_passed_rows": int(candidates["target_return_passed"].sum()),
        "target_risk_passed_rows": int(candidates["target_risk_passed"].sum()),
        "target_gate_passed_rows": int(candidates["target_gate_passed"].sum()),
        "incumbent_gate_passed_rows": int(candidates["incumbent_gate_passed"].sum()),
        "training_target_gate_passed_rows": int(training_candidates["target_gate_passed"].sum()),
        "training_incumbent_gate_passed_rows": int(
            training_candidates["incumbent_gate_passed"].sum()
        ),
        "concentration_guard_passed_rows": int(canonical["concentration_guard_passed"].sum()),
        "locked_validation_executed": locked_validation_executed,
        "locked_validation_status": (
            "PASSED" if locked_validation_passed
            else "FAILED" if locked_validation_executed
            else "NOT_EXECUTED"
        ),
        "locked_validation_passed_rows": locked_validation_passed_rows,
        "locked_validation_failed_rows": (
            len(locked_validation) - locked_validation_passed_rows
        ),
        "locked_validation_concentration_passed_rows": (
            int(locked_validation["concentration_guard_passed"].sum())
            if locked_validation_executed else 0
        ),
        "held_out_period_consumed": locked_validation_executed,
        "locked_validation_results": locked_results,
        "locked_validation_result": locked_results[0] if len(locked_results) == 1 else None,
        "incumbent_concentration_envelope": {
            key: incumbent[key] for key in ("effective_n", "top1", "top3")
        },
        "best_training_shape": {
            key: _summary_scalar(best[key]) for key in best_shape_keys + [
                "target_win_rate",
                "target_excess_p50",
                "target_excess_p10",
                "target_dd_relief_p50",
                "effective_n_p10",
                "top1_p90",
                "top3_p90",
            ]
        },
        "best_concentration_compliant_shape": (
            {
                key: _summary_scalar(best_compliant[key]) for key in best_shape_keys + [
                    "target_win_rate",
                    "target_excess_p50",
                    "target_excess_p10",
                    "target_dd_relief_p50",
                    "effective_n_p10",
                    "top1_p90",
                    "top3_p90",
                ]
            }
            if best_compliant is not None else None
        ),
        "decision": decision,
        "direction_status": direction_status,
        "locked_validation_enabled": locked_validation_executed,
        "next_research": next_research,
    }
    frames = {
        "research_seeds": seeds,
        "parameter_effects": _parameter_effects(training_candidates),
        "paired_effects": _paired_effects(
            training_candidates,
            training_windows,
            baseline_id=baseline_profile_id,
        ),
        "robust_families": _robust_families(training_candidates),
        "window_stress": _window_stress(training_windows),
        "concentration": canonical.sort_values(
            ["concentration_guard_passed", "target_excess_p50", "target_excess_p10"],
            ascending=False,
        ),
        "locked_validation": locked_validation,
        "concentration_baseline": baseline,
    }
    return frames, summary


def _json_default(value: Any):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def write_ndx_analysis_bundle(
    frames: dict[str, pd.DataFrame],
    summary: dict,
    output_dir: str | Path,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, frame in frames.items():
        filename = f"{name}.csv"
        _atomic_csv(frame, output / filename)
        files[name] = filename
    workbook_path = output / "ndx_experiment_analysis.xlsx"
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    readme = pd.DataFrame([
        {"field": key, "value": json.dumps(value, ensure_ascii=False, default=_json_default)}
        for key, value in summary.items()
    ])
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            readme.to_excel(writer, sheet_name="README", index=False)
            for name, frame in frames.items():
                frame.to_excel(writer, sheet_name=name[:31], index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    files["workbook"] = workbook_path.name
    payload = {**summary, "files": files}
    atomic_write_text(
        output / "analysis_summary.json",
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        ) + "\n",
    )
    return payload
