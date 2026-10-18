"""Point-in-time Nasdaq-100 individual-stock competition research.

The candidate asset set is the approximately 100 individual securities made
public through QQQ's SEC N-PORT filings. QQQ itself is benchmark-only. Every
selection and rebalance restores the last filing available on that date, then
uses only prior prices to rank and weight constituents.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

from backtest.engine import (
    _benchmark_label,
    _build_panels,
    _fetch_benchmark_close,
    _first_valid_price_i,
    _run_defensive_fund,
    _run_single_asset_fund,
    _run_strategy_fund,
    _vol_target_weight_series,
)
from backtest.preference import _capped_weights, _weights_for, parse_safe_weights
from backtest.preference_walkforward import (
    _load_series,
    _metric_block,
    _metrics_asof,
    _monthly_start_indexes,
    _q,
    _qs,
    _rebalance_indexes,
    _research_cfg,
    _selection_churn,
    _symbols_market_value_at,
    _symbols_value_at,
)
from backtest.ndx_quality import (
    QUALITY_POLICY_ID,
    load_quality_score_evidence,
    quality_snapshot,
    sic_capped_weights,
)
from backtest.ndx_valuation import (
    load_valuation_score_evidence,
    valuation_snapshot,
)
from backtest.risk_envelope import (
    evaluate_incumbent_risk_guard,
    evaluate_target_risk_envelope,
)
from backtest.weights import (
    WeightConstraintError,
    project_concentration_envelope_weights,
)
from core import engine as eng
from data.candidate_pool import get_nasdaq_100_snapshot
from data.ndx_history import (
    NdxHistoryError,
    constituents_asof,
    get_ndx_point_in_time_history,
    history_coverage_report,
)
from data.ndx_valuation_score import (
    SUPPORTED_VALUATION_SCORE_POLICY_IDS,
    VALUATION_SCORE_POLICY_ID,
)
from data.versioning import data_version_payload, utc_now_iso


DEFAULT_TOP_NS = (4, 6, 8, 10)
DEFAULT_WEIGHT_MODES = (
    "equal",
    "inverse_vol",
    "risk_parity",
    "score_risk",
    "source_weight",
)
DEFAULT_REBALANCE_MONTHS = (6, 12)
DEFAULT_SELECTION_MODE = "rank"
DEFAULT_QUALITY_SELECTION_MODE = "none"
SUPPORTED_QUALITY_SELECTION_MODES = (
    "none",
    "bounded_challenge",
)
DEFAULT_CORRELATION_LOOKBACK_DAYS = 252
DEFAULT_CORRELATION_THRESHOLD = 0.75
DEFAULT_CORRELATION_MIN_OBSERVATIONS = 60
SUPPORTED_SELECTION_MODES = (
    "rank",
    "correlation_replacement",
    "cluster_round_robin",
)
SUPPORTED_DEFENSE_MODES = ("static", "vol_target", "drawdown_guard")
SUPPORTED_DEFENSE_SIGNALS = (
    "risk_nav_since_start",
    "selected_basket_ex_ante_vol",
    "selected_basket_ex_ante_drawdown",
)
SUPPORTED_COMPARISON_PRIORITIES = (
    "target_then_incumbent",
    "incumbent_first",
)
MIN_UNIVERSE_PRICE_COVERAGE = 0.98
MIN_UNIVERSE_SCORE_COVERAGE = 0.85
MAX_PRICE_AGE_CALENDAR_DAYS = 7
MULTI_SECURITY_ISSUER = {
    "FOX": "FOX_CORP",
    "FOXA": "FOX_CORP",
    "GOOG": "ALPHABET",
    "GOOGL": "ALPHABET",
    "LBTYA": "LIBERTY_GLOBAL",
    "LBTYK": "LIBERTY_GLOBAL",
}


class NdxCompetitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class NdxChoice:
    mode: str
    top_n: int
    weight_mode: str
    tickers: tuple[str, ...]
    weights: dict[str, float]
    selection_date: str
    membership_evidence: dict
    expected_count: int
    expected_issuer_count: int
    price_count: int
    scored_count: int
    price_coverage: float
    score_coverage: float
    missing_price_tickers: tuple[str, ...]
    stale_price_tickers: tuple[str, ...]
    unscored_tickers: tuple[str, ...]
    duplicate_issuer_tickers: tuple[str, ...]
    selection_mode: str = DEFAULT_SELECTION_MODE
    correlation_lookback_days: int | None = None
    correlation_threshold: float | None = None
    correlation_observations: int | None = None
    correlation_price_start: str | None = None
    correlation_price_end: str | None = None
    correlation_strict_asof_passed: bool | None = None
    correlation_pool_size: int | None = None
    max_names_per_cluster: int | None = None
    cluster_max_weight: float | None = None
    top_weight_count: int | None = None
    top_weight_cap: float | None = None
    min_effective_n: float | None = None
    cluster_labels: dict[str, int] | None = None
    cluster_weights: dict[int, float] | None = None
    max_pair_correlation: float | None = None
    rejected_correlated_tickers: tuple[str, ...] = ()
    fundamental_score_weight: float = 0.0
    quality_policy_id: str | None = None
    quality_score_coverage: float | None = None
    quality_score_date: str | None = None
    quality_future_data_guard_passed: bool | None = None
    quality_selection_mode: str = DEFAULT_QUALITY_SELECTION_MODE
    quality_challenge_pool_size: int | None = None
    max_quality_replacements: int = 0
    quality_challenge_pool_tickers: tuple[str, ...] = ()
    quality_replacement_pairs: tuple[dict[str, Any], ...] = ()
    valuation_score_weight: float = 0.0
    valuation_policy_id: str | None = None
    valuation_score_coverage: float | None = None
    valuation_observed_coverage: float | None = None
    valuation_score_date: str | None = None
    valuation_future_data_guard_passed: bool | None = None
    valuation_missing_neutral_count: int = 0
    max_names_per_sic4: int | None = None
    max_names_per_sic2: int | None = None
    sic4_max_weight: float | None = None
    sic2_max_weight: float | None = None
    sic4_by_ticker: dict[str, int] | None = None
    sic2_by_ticker: dict[str, str] | None = None
    sic4_weights: dict[int, float] | None = None
    sic2_weights: dict[str, float] | None = None
    rejected_sic_tickers: tuple[str, ...] = ()
    rejected_sic_reasons: dict[str, str] | None = None
    candidate_tickers: tuple[str, ...] = ()
    candidate_member_count: int | None = None


def _parse_ints(value: str | Iterable[int], default: Iterable[int]) -> list[int]:
    if isinstance(value, str):
        parts = value.replace("，", ",").replace(";", ",").split(",")
        values = [int(float(part.strip())) for part in parts if part.strip()]
    else:
        values = [int(item) for item in value]
    return sorted({item for item in values if item > 0}) or sorted(set(default))


def _parse_modes(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        parts = value.replace("，", ",").replace(";", ",").split(",")
    else:
        parts = list(value)
    modes = []
    for part in parts:
        mode = str(part or "").strip().lower()
        if mode and mode not in modes:
            modes.append(mode)
    invalid = sorted(set(modes) - set(DEFAULT_WEIGHT_MODES))
    if invalid:
        raise NdxCompetitionError(f"unsupported NDX weight modes: {invalid}")
    return modes or list(DEFAULT_WEIGHT_MODES)


def _parse_candidate_tickers(
    value: str | Iterable[str] | None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    parts = value.replace(",", ";").split(";") if isinstance(value, str) else value
    return tuple(sorted({
        str(item or "").strip().upper()
        for item in parts
        if str(item or "").strip()
    }))


def _parse_weight_caps(value: str | Iterable[float]) -> list[float]:
    values = parse_safe_weights(value)
    caps = sorted({float(item) for item in values})
    if not caps or any(not np.isfinite(item) or item <= 0 or item > 1 for item in caps):
        raise NdxCompetitionError("max weights must be finite values in (0, 1]")
    return caps


def _normalize_construction_profiles(
    profiles: Iterable[Mapping[str, Any]] | None,
    *,
    lookback_years: float,
    top_values: Iterable[int],
    mode_values: Iterable[str],
    safe_values: Iterable[float],
    rebalance_values: Iterable[int],
    max_weight_values: Iterable[float],
) -> list[dict[str, Any]]:
    """Return explicit v4 profiles or backward-compatible legacy grid rows."""
    if profiles is None:
        return [
            {
                "profile_id": None,
                "top_n": int(top_n),
                "weight_mode": str(mode),
                "rebalance_months": int(rebalance),
                "safe_weight": float(safe_weight),
                "challenger_sleeve_weight": 1.0,
                "max_weight": float(max_weight),
                "min_weight": 0.02,
                "selection_mode": DEFAULT_SELECTION_MODE,
                "correlation_lookback_days": None,
                "correlation_threshold": None,
                "correlation_pool_size": None,
                "max_names_per_cluster": None,
                "cluster_max_weight": None,
                "top_weight_count": None,
                "top_weight_cap": None,
                "min_effective_n": None,
                "fundamental_score_weight": 0.0,
                "quality_policy_id": None,
                "valuation_score_weight": 0.0,
                "valuation_policy_id": None,
                "quality_selection_mode": DEFAULT_QUALITY_SELECTION_MODE,
                "quality_challenge_pool_size": None,
                "max_quality_replacements": 0,
                "max_names_per_sic4": None,
                "max_names_per_sic2": None,
                "sic4_max_weight": None,
                "sic2_max_weight": None,
                "candidate_tickers": (),
                "defense_mode": "static",
                "defense_signal": None,
                "target_vol": None,
                "defense_band": None,
                "defense_vol_window": None,
                "defense_exec_band": None,
                "defense_drawdown_lookback_days": None,
                "defense_drawdown_trigger": None,
                "defense_drawdown_full": None,
                "defense_max_safe_weight": None,
                "defense_release_step": None,
                "explicit_profile": False,
            }
            for top_n in top_values
            for mode in mode_values
            for rebalance in rebalance_values
            for safe_weight in safe_values
            for max_weight in max_weight_values
        ]

    normalized = []
    seen_ids = set()
    for index, raw in enumerate(profiles, start=1):
        if not isinstance(raw, Mapping):
            raise NdxCompetitionError(
                f"construction profile {index} must be a mapping"
            )
        profile_id = str(raw.get("id") or raw.get("profile_id") or "").strip()
        if not profile_id or profile_id in seen_ids:
            raise NdxCompetitionError(
                f"construction profile id is empty or duplicated: {profile_id!r}"
            )
        seen_ids.add(profile_id)
        top_n = int(raw.get("top_n") or 0)
        weight_mode = str(raw.get("weight_mode") or "").strip().lower()
        rebalance = int(raw.get("rebalance_months") or 0)
        safe_weight = float(raw.get("safe_weight") or 0.0)
        challenger_sleeve_weight = float(
            raw.get("challenger_sleeve_weight", 1.0)
        )
        max_weight = float(raw.get("max_weight") or 0.0)
        min_weight = float(raw.get("min_weight", 0.02))
        selection_mode = str(
            raw.get("selection_mode") or DEFAULT_SELECTION_MODE
        ).strip().lower()
        corr_lookback = int(
            raw.get("correlation_lookback_days")
            or DEFAULT_CORRELATION_LOOKBACK_DAYS
        )
        corr_threshold = float(
            raw.get("correlation_threshold", DEFAULT_CORRELATION_THRESHOLD)
        )
        corr_pool_size = int(raw.get("correlation_pool_size") or 0)
        max_names = int(raw.get("max_names_per_cluster") or 1)
        raw_cluster_cap = raw.get("cluster_max_weight")
        cluster_cap = (
            None if raw_cluster_cap is None else float(raw_cluster_cap)
        )
        raw_top_weight_count = raw.get("top_weight_count")
        raw_top_weight_cap = raw.get("top_weight_cap")
        raw_min_effective_n = raw.get("min_effective_n")
        top_weight_count = (
            None if raw_top_weight_count is None else int(raw_top_weight_count)
        )
        top_weight_cap = (
            None if raw_top_weight_cap is None else float(raw_top_weight_cap)
        )
        min_effective_n = (
            None if raw_min_effective_n is None else float(raw_min_effective_n)
        )
        defense_mode = str(raw.get("defense_mode") or "static").strip().lower()
        defense_signal = str(
            raw.get("defense_signal") or "risk_nav_since_start"
        ).strip().lower()
        target_vol = float(raw.get("target_vol", 0.25))
        defense_band = float(raw.get("defense_band", 0.15))
        defense_vol_window = int(raw.get("defense_vol_window", 20))
        defense_exec_band = float(raw.get("defense_exec_band", 0.15))
        defense_drawdown_lookback_days = int(
            raw.get("defense_drawdown_lookback_days") or 126
        )
        defense_drawdown_trigger = float(
            raw.get("defense_drawdown_trigger", 0.05)
        )
        defense_drawdown_full = float(raw.get("defense_drawdown_full", 0.15))
        defense_max_safe_weight = float(
            raw.get("defense_max_safe_weight", 0.30)
        )
        raw_release_step = raw.get("defense_release_step")
        defense_release_step = (
            None if raw_release_step is None else float(raw_release_step)
        )
        fundamental_score_weight = float(
            raw.get("fundamental_score_weight", 0.0)
        )
        valuation_score_weight = float(raw.get("valuation_score_weight", 0.0))
        valuation_policy_id = (
            str(raw.get("valuation_policy_id") or "").strip() or None
        )
        quality_selection_mode = str(
            raw.get("quality_selection_mode")
            or DEFAULT_QUALITY_SELECTION_MODE
        ).strip().lower()
        raw_quality_pool_size = raw.get("quality_challenge_pool_size")
        quality_challenge_pool_size = (
            None
            if raw_quality_pool_size is None
            else int(raw_quality_pool_size)
        )
        max_quality_replacements = int(
            raw.get("max_quality_replacements") or 0
        )
        raw_sic4_names = raw.get("max_names_per_sic4")
        raw_sic2_names = raw.get("max_names_per_sic2")
        max_names_per_sic4 = (
            None if raw_sic4_names is None else int(raw_sic4_names)
        )
        max_names_per_sic2 = (
            None if raw_sic2_names is None else int(raw_sic2_names)
        )
        raw_sic4_weight = raw.get("sic4_max_weight")
        raw_sic2_weight = raw.get("sic2_max_weight")
        sic4_max_weight = (
            None if raw_sic4_weight is None else float(raw_sic4_weight)
        )
        sic2_max_weight = (
            None if raw_sic2_weight is None else float(raw_sic2_weight)
        )
        candidate_tickers = _parse_candidate_tickers(raw.get("candidate_tickers"))
        quality_required = bool(
            fundamental_score_weight > 0
            or raw.get("quality_policy_id") is not None
            or quality_selection_mode != DEFAULT_QUALITY_SELECTION_MODE
            or max_names_per_sic4 is not None
            or max_names_per_sic2 is not None
            or sic4_max_weight is not None
            or sic2_max_weight is not None
        )
        quality_policy_id = (
            str(raw.get("quality_policy_id") or QUALITY_POLICY_ID).strip()
            if quality_required else None
        )

        if top_n < 2:
            raise NdxCompetitionError(f"{profile_id}: top_n must be at least 2")
        if candidate_tickers and len(candidate_tickers) < top_n:
            raise NdxCompetitionError(
                f"{profile_id}: candidate_tickers has only {len(candidate_tickers)} "
                f"names for top{top_n}"
            )
        if weight_mode not in DEFAULT_WEIGHT_MODES:
            raise NdxCompetitionError(
                f"{profile_id}: unsupported weight mode {weight_mode!r}"
            )
        if rebalance <= 0:
            raise NdxCompetitionError(
                f"{profile_id}: rebalance_months must be positive"
            )
        if not 0.0 <= safe_weight <= 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: safe_weight must be in [0, 1]"
            )
        if not np.isfinite(challenger_sleeve_weight) or not (
            0.0 < challenger_sleeve_weight <= 1.0
        ):
            raise NdxCompetitionError(
                f"{profile_id}: challenger_sleeve_weight must be in (0, 1]"
            )
        if not np.isfinite(max_weight) or not 0.0 < max_weight <= 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: max_weight must be in (0, 1]"
            )
        if not np.isfinite(min_weight) or not 0.0 <= min_weight <= 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: min_weight must be in [0, 1]"
            )
        if selection_mode not in SUPPORTED_SELECTION_MODES:
            raise NdxCompetitionError(
                f"{profile_id}: unsupported selection mode {selection_mode!r}"
            )
        correlation_required = (
            selection_mode != DEFAULT_SELECTION_MODE or cluster_cap is not None
        )
        if correlation_required:
            if corr_lookback <= DEFAULT_CORRELATION_MIN_OBSERVATIONS:
                raise NdxCompetitionError(
                    f"{profile_id}: correlation lookback is too short"
                )
            if not 0.0 < corr_threshold < 1.0:
                raise NdxCompetitionError(
                    f"{profile_id}: correlation threshold must be in (0, 1)"
                )
            if corr_pool_size and corr_pool_size < top_n:
                raise NdxCompetitionError(
                    f"{profile_id}: correlation_pool_size must be 0 or >= top_n"
                )
            if max_names < 1:
                raise NdxCompetitionError(
                    f"{profile_id}: max_names_per_cluster must be positive"
                )
        if cluster_cap is not None:
            if not np.isfinite(cluster_cap) or not 0.0 < cluster_cap <= 1.0:
                raise NdxCompetitionError(
                    f"{profile_id}: cluster_max_weight must be in (0, 1]"
                )
            effective_floor = min(max(0.0, min_weight), 1.0 / top_n)
            if cluster_cap < effective_floor:
                raise NdxCompetitionError(
                    f"{profile_id}: cluster cap is below the effective ticker floor"
                )
        envelope_declared = (
            top_weight_count is not None
            or top_weight_cap is not None
            or min_effective_n is not None
        )
        if (top_weight_count is None) != (top_weight_cap is None):
            raise NdxCompetitionError(
                f"{profile_id}: top_weight_count and top_weight_cap must be "
                "declared together"
            )
        if envelope_declared:
            if weight_mode != "source_weight":
                raise NdxCompetitionError(
                    f"{profile_id}: concentration-envelope projection requires "
                    "source_weight"
                )
            if top_weight_count is None or top_weight_cap is None:
                raise NdxCompetitionError(
                    f"{profile_id}: min_effective_n requires a top-weight envelope"
                )
            if not 1 <= top_weight_count < top_n:
                raise NdxCompetitionError(
                    f"{profile_id}: top_weight_count must be in [1, top_n)"
                )
            if (
                not np.isfinite(top_weight_cap)
                or not top_weight_count / top_n <= top_weight_cap <= 1.0
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: top_weight_cap is infeasible for top_n"
                )
            if min_effective_n is not None and (
                not np.isfinite(min_effective_n)
                or not 1.0 <= min_effective_n <= top_n
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: min_effective_n must be in [1, top_n]"
                )
            if cluster_cap is not None:
                raise NdxCompetitionError(
                    f"{profile_id}: concentration envelope and cluster cap "
                    "cannot be combined"
                )
        if not 0.0 <= fundamental_score_weight <= 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: fundamental_score_weight must be in [0, 1]"
            )
        if not 0.0 <= valuation_score_weight <= 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: valuation_score_weight must be in [0, 1]"
            )
        if fundamental_score_weight + valuation_score_weight > 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: quality plus valuation weights exceed 1"
            )
        if valuation_score_weight > 0 and (
            valuation_policy_id not in SUPPORTED_VALUATION_SCORE_POLICY_IDS
        ):
            raise NdxCompetitionError(
                f"{profile_id}: unsupported valuation policy {valuation_policy_id!r}"
            )
        if quality_selection_mode not in SUPPORTED_QUALITY_SELECTION_MODES:
            raise NdxCompetitionError(
                f"{profile_id}: unsupported quality selection mode "
                f"{quality_selection_mode!r}"
            )
        if quality_selection_mode == DEFAULT_QUALITY_SELECTION_MODE:
            if (
                quality_challenge_pool_size is not None
                or max_quality_replacements != 0
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: inactive quality selection cannot declare "
                    "a challenge pool or replacement budget"
                )
        else:
            if selection_mode != DEFAULT_SELECTION_MODE:
                raise NdxCompetitionError(
                    f"{profile_id}: bounded quality challenge requires rank selection"
                )
            if fundamental_score_weight != 0.0 or valuation_score_weight != 0.0:
                raise NdxCompetitionError(
                    f"{profile_id}: bounded quality challenge cannot be combined "
                    "with score blends"
                )
            if (
                quality_challenge_pool_size is None
                or quality_challenge_pool_size <= top_n
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: quality_challenge_pool_size must exceed top_n"
                )
            available_challengers = quality_challenge_pool_size - top_n
            if not 1 <= max_quality_replacements <= min(
                top_n, available_challengers
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: max_quality_replacements exceeds the "
                    "declared baseline or challenge pool"
                )
        if quality_required and quality_policy_id != QUALITY_POLICY_ID:
            raise NdxCompetitionError(
                f"{profile_id}: quality policy must be {QUALITY_POLICY_ID}"
            )
        for label, value in (
            ("max_names_per_sic4", max_names_per_sic4),
            ("max_names_per_sic2", max_names_per_sic2),
        ):
            if value is not None and value < 1:
                raise NdxCompetitionError(
                    f"{profile_id}: {label} must be positive"
                )
        for label, value in (
            ("sic4_max_weight", sic4_max_weight),
            ("sic2_max_weight", sic2_max_weight),
        ):
            if value is not None and (
                not np.isfinite(value) or not 0.0 < value <= 1.0
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: {label} must be in (0, 1]"
                )
        sic_name_caps = (
            max_names_per_sic4 is not None or max_names_per_sic2 is not None
        )
        sic_weight_caps = (
            sic4_max_weight is not None or sic2_max_weight is not None
        )
        if (sic_name_caps or sic_weight_caps) and selection_mode != "rank":
            raise NdxCompetitionError(
                f"{profile_id}: SIC constraints currently require rank selection"
            )
        if sic_name_caps and quality_selection_mode != DEFAULT_QUALITY_SELECTION_MODE:
            raise NdxCompetitionError(
                f"{profile_id}: SIC name replacement cannot be combined with a "
                "bounded quality replacement budget"
            )
        if sic_weight_caps and cluster_cap is not None:
            raise NdxCompetitionError(
                f"{profile_id}: SIC and cluster weight caps cannot be combined"
            )
        if sic_weight_caps and envelope_declared:
            raise NdxCompetitionError(
                f"{profile_id}: SIC weight caps and concentration envelope "
                "cannot be combined"
            )
        if defense_mode not in SUPPORTED_DEFENSE_MODES:
            raise NdxCompetitionError(
                f"{profile_id}: unsupported defense mode {defense_mode!r}"
            )
        if defense_mode == "vol_target":
            if defense_signal not in SUPPORTED_DEFENSE_SIGNALS:
                raise NdxCompetitionError(
                    f"{profile_id}: unsupported defense signal {defense_signal!r}"
                )
            if not np.isfinite(target_vol) or target_vol <= 0:
                raise NdxCompetitionError(
                    f"{profile_id}: target_vol must be positive"
                )
            if (
                not np.isfinite(defense_band)
                or defense_band < 0
                or safe_weight + defense_band > 1.0
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: dynamic safe-weight band exceeds [0, 1]"
                )
            if defense_vol_window < 2:
                raise NdxCompetitionError(
                    f"{profile_id}: defense_vol_window must be at least 2"
                )
            if not 0.0 <= defense_exec_band <= 1.0:
                raise NdxCompetitionError(
                    f"{profile_id}: defense_exec_band must be in [0, 1]"
                )
        if defense_mode == "drawdown_guard":
            if defense_signal != "selected_basket_ex_ante_drawdown":
                raise NdxCompetitionError(
                    f"{profile_id}: drawdown guard requires selected-basket signal"
                )
            if defense_drawdown_lookback_days < 20:
                raise NdxCompetitionError(
                    f"{profile_id}: drawdown lookback must be at least 20 days"
                )
            if not (
                0.0 <= defense_drawdown_trigger < defense_drawdown_full <= 1.0
            ):
                raise NdxCompetitionError(
                    f"{profile_id}: drawdown trigger/full thresholds are invalid"
                )
            if not safe_weight <= defense_max_safe_weight <= 1.0:
                raise NdxCompetitionError(
                    f"{profile_id}: maximum safe weight is below its base"
                )
            if not 0.0 <= defense_exec_band <= 1.0:
                raise NdxCompetitionError(
                    f"{profile_id}: defense_exec_band must be in [0, 1]"
                )
        if defense_release_step is not None and not 0.0 < defense_release_step <= 1.0:
            raise NdxCompetitionError(
                f"{profile_id}: defense_release_step must be in (0, 1]"
            )

        normalized.append({
            "profile_id": profile_id,
            "top_n": top_n,
            "weight_mode": weight_mode,
            "rebalance_months": rebalance,
            "safe_weight": safe_weight,
            "challenger_sleeve_weight": challenger_sleeve_weight,
            "max_weight": max_weight,
            "min_weight": min_weight,
            "selection_mode": selection_mode,
            "correlation_lookback_days": corr_lookback if correlation_required else None,
            "correlation_threshold": corr_threshold if correlation_required else None,
            "correlation_pool_size": corr_pool_size if correlation_required else None,
            "max_names_per_cluster": max_names if correlation_required else None,
            "cluster_max_weight": cluster_cap,
            "top_weight_count": top_weight_count,
            "top_weight_cap": top_weight_cap,
            "min_effective_n": min_effective_n,
            "fundamental_score_weight": fundamental_score_weight,
            "quality_policy_id": quality_policy_id,
            "valuation_score_weight": valuation_score_weight,
            "valuation_policy_id": valuation_policy_id,
            "quality_selection_mode": quality_selection_mode,
            "quality_challenge_pool_size": quality_challenge_pool_size,
            "max_quality_replacements": max_quality_replacements,
            "max_names_per_sic4": max_names_per_sic4,
            "max_names_per_sic2": max_names_per_sic2,
            "sic4_max_weight": sic4_max_weight,
            "sic2_max_weight": sic2_max_weight,
            "candidate_tickers": candidate_tickers,
            "defense_mode": defense_mode,
            "defense_signal": (
                defense_signal if defense_mode in {"vol_target", "drawdown_guard"} else None
            ),
            "target_vol": target_vol if defense_mode == "vol_target" else None,
            "defense_band": defense_band if defense_mode == "vol_target" else None,
            "defense_vol_window": (
                defense_vol_window if defense_mode == "vol_target" else None
            ),
            "defense_exec_band": (
                defense_exec_band
                if defense_mode in {"vol_target", "drawdown_guard"} else None
            ),
            "defense_drawdown_lookback_days": (
                defense_drawdown_lookback_days
                if defense_mode == "drawdown_guard" else None
            ),
            "defense_drawdown_trigger": (
                defense_drawdown_trigger if defense_mode == "drawdown_guard" else None
            ),
            "defense_drawdown_full": (
                defense_drawdown_full if defense_mode == "drawdown_guard" else None
            ),
            "defense_max_safe_weight": (
                defense_max_safe_weight if defense_mode == "drawdown_guard" else None
            ),
            "defense_release_step": (
                defense_release_step
                if defense_mode in {"vol_target", "drawdown_guard"} else None
            ),
            "explicit_profile": True,
            "lookback_years": float(lookback_years),
        })
    if not normalized:
        raise NdxCompetitionError("construction_profiles must not be empty")
    return normalized


def _profile_requires_quality_evidence(profile: Mapping[str, Any]) -> bool:
    return bool(
        float(profile.get("fundamental_score_weight") or 0.0) > 0
        or profile.get("quality_policy_id") is not None
        or str(
            profile.get("quality_selection_mode")
            or DEFAULT_QUALITY_SELECTION_MODE
        ) != DEFAULT_QUALITY_SELECTION_MODE
        or profile.get("max_names_per_sic4") is not None
        or profile.get("max_names_per_sic2") is not None
        or profile.get("sic4_max_weight") is not None
        or profile.get("sic2_max_weight") is not None
    )


def _profile_requires_valuation_evidence(profile: Mapping[str, Any]) -> bool:
    return bool(float(profile.get("valuation_score_weight") or 0.0) > 0)


def _valuation_policy_for_profiles(profiles: Iterable[Mapping[str, Any]]) -> str | None:
    policies = {
        str(profile.get("valuation_policy_id") or "")
        for profile in profiles
        if _profile_requires_valuation_evidence(profile)
    }
    if not policies:
        return None
    if len(policies) != 1 or "" in policies:
        raise NdxCompetitionError(
            "one experiment job must use exactly one non-empty valuation policy"
        )
    policy_id = next(iter(policies))
    if policy_id not in SUPPORTED_VALUATION_SCORE_POLICY_IDS:
        raise NdxCompetitionError(f"unsupported valuation policy: {policy_id}")
    return policy_id


def _issuer_key(ticker: str) -> str:
    normalized = str(ticker or "").upper().strip()
    return MULTI_SECURITY_ISSUER.get(normalized, normalized)


def _select_bounded_quality_challengers(
    price_ranked: list[str],
    quality_scores: pd.DataFrame,
    *,
    top_n: int,
    pool_size: int,
    max_replacements: int,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Improve quality within a fixed price-ranked pool and replacement budget."""
    if len(price_ranked) < int(pool_size):
        raise NdxCompetitionError(
            f"quality challenge pool has only {len(price_ranked)} names for "
            f"declared size {int(pool_size)}"
        )
    pool = list(price_ranked[:int(pool_size)])
    baseline = pool[:int(top_n)]
    challenge = pool[int(top_n):]
    missing_columns = {"quality_score", "quality_eligible"} - set(
        quality_scores.columns
    )
    if missing_columns:
        raise NdxCompetitionError(
            f"quality challenge evidence missing columns: {sorted(missing_columns)}"
        )
    numeric_quality = pd.to_numeric(
        quality_scores["quality_score"], errors="coerce"
    )
    eligible = quality_scores["quality_eligible"].eq(True)
    score_by_ticker = numeric_quality[eligible & numeric_quality.notna()].to_dict()
    price_rank = {ticker: index + 1 for index, ticker in enumerate(pool)}

    outgoing = sorted(
        (ticker for ticker in baseline if ticker in score_by_ticker),
        key=lambda ticker: (
            float(score_by_ticker[ticker]),
            -int(price_rank[ticker]),
            ticker,
        ),
    )
    incoming = sorted(
        (ticker for ticker in challenge if ticker in score_by_ticker),
        key=lambda ticker: (
            -float(score_by_ticker[ticker]),
            int(price_rank[ticker]),
            ticker,
        ),
    )
    replacements = []
    for outgoing_ticker, incoming_ticker in zip(outgoing, incoming):
        if len(replacements) >= int(max_replacements):
            break
        outgoing_score = float(score_by_ticker[outgoing_ticker])
        incoming_score = float(score_by_ticker[incoming_ticker])
        if incoming_score <= outgoing_score:
            break
        replacements.append({
            "outgoing_ticker": outgoing_ticker,
            "incoming_ticker": incoming_ticker,
            "outgoing_price_rank": int(price_rank[outgoing_ticker]),
            "incoming_price_rank": int(price_rank[incoming_ticker]),
            "outgoing_quality_score": outgoing_score,
            "incoming_quality_score": incoming_score,
            "quality_score_delta": incoming_score - outgoing_score,
        })

    selected = set(baseline)
    for replacement in replacements:
        selected.remove(replacement["outgoing_ticker"])
        selected.add(replacement["incoming_ticker"])
    picked = [ticker for ticker in pool if ticker in selected]
    if len(picked) != int(top_n):
        raise NdxCompetitionError("bounded quality challenge changed ticker count")
    return picked, pool, replacements


def _select_ranked_with_sic_caps(
    ranked: list[str],
    classifications: pd.DataFrame,
    *,
    top_n: int,
    max_names_per_sic4: int | None,
    max_names_per_sic2: int | None,
) -> tuple[list[str], dict[str, str]]:
    selected = []
    rejected = {}
    sic4_counts: dict[int, int] = {}
    sic2_counts: dict[str, int] = {}
    for ticker in ranked:
        if ticker not in classifications.index:
            raise NdxCompetitionError(f"SIC classification missing for {ticker}")
        row = classifications.loc[ticker]
        sic4 = int(row["sic"])
        sic2 = str(row["sic_group_2d"])
        reason = None
        if (
            max_names_per_sic4 is not None
            and sic4_counts.get(sic4, 0) >= int(max_names_per_sic4)
        ):
            reason = "sic4_name_cap"
        elif (
            max_names_per_sic2 is not None
            and sic2_counts.get(sic2, 0) >= int(max_names_per_sic2)
        ):
            reason = "sic2_name_cap"
        if reason:
            rejected[ticker] = reason
            continue
        selected.append(ticker)
        sic4_counts[sic4] = sic4_counts.get(sic4, 0) + 1
        sic2_counts[sic2] = sic2_counts.get(sic2, 0) + 1
        if len(selected) >= int(top_n):
            break
    if len(selected) != int(top_n):
        raise NdxCompetitionError(
            f"SIC name caps selected {len(selected)} names for top{top_n}"
        )
    return selected, rejected


def _price_universe_version(series: Mapping[str, pd.DataFrame]) -> dict:
    digest = hashlib.sha256()
    rows = 0
    starts = []
    ends = []
    for ticker in sorted(series):
        frame = series[ticker].sort_index()
        columns = [name for name in ("Open", "High", "Low", "Close") if name in frame]
        values = frame[columns]
        digest.update(ticker.encode("ascii"))
        digest.update("|".join(columns).encode("ascii"))
        digest.update(pd.util.hash_pandas_object(values, index=True).values.tobytes())
        rows += len(values)
        if not values.empty:
            starts.append(values.index[0])
            ends.append(values.index[-1])
    return {
        "version_id": f"ndx_price_universe:{digest.hexdigest()[:16]}",
        "content_sha256": digest.hexdigest(),
        "ticker_count": len(series),
        "row_count": int(rows),
        "data_start": min(starts).strftime("%Y-%m-%d") if starts else None,
        "data_end": max(ends).strftime("%Y-%m-%d") if ends else None,
    }


def _returns_before(
    series: Mapping[str, pd.DataFrame],
    tickers: Iterable[str],
    asof: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    columns = {}
    for ticker in tickers:
        frame = series.get(ticker)
        if frame is None:
            continue
        close = frame["Close"]
        history = close[close.index < pd.Timestamp(asof)].dropna().tail(int(lookback_days) + 1)
        if len(history) >= 61:
            columns[ticker] = history
    if not columns:
        return pd.DataFrame()
    prices = pd.concat(columns, axis=1).ffill().dropna(how="any")
    return prices.pct_change(fill_method=None).dropna(how="any")


def _correlation_before(
    series: Mapping[str, pd.DataFrame],
    tickers: Iterable[str],
    asof: pd.Timestamp,
    *,
    lookback_days: int,
    min_observations: int = DEFAULT_CORRELATION_MIN_OBSERVATIONS,
    cache: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    names = tuple(sorted({str(ticker).upper() for ticker in tickers}))
    if len(names) < 2:
        raise NdxCompetitionError("correlation selection requires at least two tickers")
    asof_date = pd.Timestamp(asof)
    key = (
        asof_date.strftime("%Y-%m-%d"),
        names,
        int(lookback_days),
        int(min_observations),
    )
    if cache is not None and key in cache:
        return cache[key]

    columns = {}
    for ticker in names:
        frame = series.get(ticker)
        if frame is None or "Close" not in frame:
            raise NdxCompetitionError(
                f"correlation price history is missing for {ticker}"
            )
        history = frame["Close"]
        history = history[history.index < asof_date].dropna().tail(int(lookback_days) + 1)
        if len(history) < int(min_observations) + 1:
            raise NdxCompetitionError(
                f"correlation history for {ticker} has only {len(history) - 1} returns"
            )
        columns[ticker] = history
    prices = pd.concat(columns, axis=1).ffill().dropna(how="any")
    prices = prices.tail(int(lookback_days) + 1)
    returns = prices.pct_change(fill_method=None).dropna(how="any")
    if len(returns) < int(min_observations):
        raise NdxCompetitionError(
            f"correlation matrix has only {len(returns)} common observations"
        )
    if (returns.std(ddof=1) <= 0).any():
        raise NdxCompetitionError("zero-variance returns cannot be clustered")
    corr = returns.corr().clip(-1.0, 1.0)
    if corr.isna().any().any() or not np.isfinite(corr.to_numpy(dtype=float)).all():
        raise NdxCompetitionError("correlation matrix contains non-finite values")
    np.fill_diagonal(corr.values, 1.0)
    meta = {
        "observations": int(len(returns)),
        "price_start": prices.index[0].strftime("%Y-%m-%d"),
        "price_end": prices.index[-1].strftime("%Y-%m-%d"),
        "strict_asof_passed": bool(prices.index[-1] < asof_date),
    }
    if not meta["strict_asof_passed"]:
        raise NdxCompetitionError("correlation prices are not strictly before selection")
    result = (corr, meta)
    if cache is not None:
        cache[key] = result
    return result


def _complete_linkage_clusters(
    corr: pd.DataFrame,
    threshold: float,
) -> dict[str, int]:
    if len(corr) == 1:
        return {str(corr.index[0]): 1}
    if list(corr.index) != list(corr.columns):
        raise NdxCompetitionError("correlation matrix axes do not match")
    distance = np.clip(1.0 - corr.to_numpy(dtype=float), 0.0, 2.0)
    np.fill_diagonal(distance, 0.0)
    raw_labels = fcluster(
        linkage(squareform(distance, checks=True), method="complete"),
        t=1.0 - float(threshold),
        criterion="distance",
    )
    raw_groups: dict[int, list[str]] = {}
    for ticker, label in zip(corr.index, raw_labels):
        raw_groups.setdefault(int(label), []).append(str(ticker))
    ordered_groups = sorted(tuple(sorted(names)) for names in raw_groups.values())
    return {
        ticker: cluster_id
        for cluster_id, names in enumerate(ordered_groups, start=1)
        for ticker in names
    }


def _select_with_correlation(
    ranked: list[str],
    corr: pd.DataFrame,
    *,
    top_n: int,
    selection_mode: str,
    threshold: float,
    max_names_per_cluster: int,
) -> tuple[list[str], dict[str, int], list[str]]:
    if selection_mode == "correlation_replacement":
        picked = []
        rejected = []
        for ticker in ranked:
            if picked and any(
                float(corr.loc[ticker, held]) >= float(threshold)
                for held in picked
            ):
                rejected.append(ticker)
                continue
            picked.append(ticker)
            if len(picked) == int(top_n):
                break
        if len(picked) < int(top_n):
            raise NdxCompetitionError(
                f"correlation replacement filled only {len(picked)} of top{top_n}"
            )
        labels = _complete_linkage_clusters(corr.loc[picked, picked], threshold)
        return picked, labels, rejected

    if selection_mode != "cluster_round_robin":
        raise NdxCompetitionError(
            f"unsupported correlation selection mode: {selection_mode}"
        )
    labels = _complete_linkage_clusters(corr, threshold)
    groups: dict[int, list[str]] = {}
    for ticker in ranked:
        groups.setdefault(labels[ticker], []).append(ticker)
    ordered_groups = sorted(groups.values(), key=lambda names: ranked.index(names[0]))
    picked = []
    for level in range(int(max_names_per_cluster)):
        for names in ordered_groups:
            if level < len(names):
                picked.append(names[level])
                if len(picked) == int(top_n):
                    selected_labels = {ticker: labels[ticker] for ticker in picked}
                    return picked, selected_labels, []
    raise NdxCompetitionError(
        f"cluster round-robin filled only {len(picked)} of top{top_n}; "
        f"max_names_per_cluster={max_names_per_cluster}"
    )


def _bounded_scaled_allocation(
    raw: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    *,
    total: float,
    tolerance: float = 1e-12,
) -> np.ndarray:
    raw = np.asarray(raw, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    if not (
        len(raw) == len(lower) == len(upper)
        and np.isfinite(raw).all()
        and np.isfinite(lower).all()
        and np.isfinite(upper).all()
    ):
        raise NdxCompetitionError("cluster weight bounds are invalid")
    if (lower < 0).any() or (upper < lower).any():
        raise NdxCompetitionError("cluster weight bounds are infeasible")
    if float(lower.sum()) > total + tolerance or float(upper.sum()) < total - tolerance:
        raise NdxCompetitionError("cluster weight budget cannot sum to one")
    positive = np.clip(raw, 0.0, None)
    if float(positive.sum()) <= 0:
        positive = np.ones(len(raw), dtype=float)

    low_scale = 0.0
    high_scale = 1.0
    while float(np.clip(high_scale * positive, lower, upper).sum()) < total:
        high_scale *= 2.0
        if high_scale > 1e18:
            raise NdxCompetitionError("cluster weight projection did not converge")
    for _ in range(160):
        scale = (low_scale + high_scale) / 2.0
        value = float(np.clip(scale * positive, lower, upper).sum())
        if value < total:
            low_scale = scale
        else:
            high_scale = scale
    weights = np.clip(high_scale * positive, lower, upper)
    residual = float(total - weights.sum())
    if abs(residual) > tolerance:
        room = upper - weights if residual > 0 else weights - lower
        for index in np.flatnonzero(room > tolerance):
            adjustment = min(abs(residual), float(room[index]))
            weights[index] += adjustment if residual > 0 else -adjustment
            residual += -adjustment if residual > 0 else adjustment
            if abs(residual) <= tolerance:
                break
    if not np.isclose(float(weights.sum()), total, atol=1e-10, rtol=0.0):
        raise NdxCompetitionError("cluster weights do not sum to one")
    return weights


def _cluster_capped_weights(
    raw: pd.Series,
    cluster_labels: Mapping[str, int],
    *,
    cluster_max_weight: float,
    max_weight: float,
    min_weight: float,
) -> pd.Series:
    tickers = list(raw.index)
    if set(cluster_labels) != set(tickers):
        raise NdxCompetitionError("cluster labels do not match selected tickers")
    count = len(tickers)
    floor = min(max(0.0, float(min_weight)), 1.0 / count)
    cap = min(1.0, max(float(max_weight), 1.0 / count))
    cluster_ids = sorted(set(int(cluster_labels[ticker]) for ticker in tickers))
    members = {
        cluster_id: [
            index for index, ticker in enumerate(tickers)
            if int(cluster_labels[ticker]) == cluster_id
        ]
        for cluster_id in cluster_ids
    }
    raw_values = raw.astype(float).to_numpy()
    cluster_raw = np.asarray([
        float(np.clip(raw_values[indexes], 0.0, None).sum())
        for indexes in members.values()
    ])
    cluster_lower = np.asarray([len(indexes) * floor for indexes in members.values()])
    cluster_upper = np.asarray([
        min(float(cluster_max_weight), len(indexes) * cap)
        for indexes in members.values()
    ])
    cluster_totals = _bounded_scaled_allocation(
        cluster_raw,
        cluster_lower,
        cluster_upper,
        total=1.0,
    )
    weights = np.zeros(count, dtype=float)
    for cluster_total, indexes in zip(cluster_totals, members.values()):
        weights[indexes] = _bounded_scaled_allocation(
            raw_values[indexes],
            np.repeat(floor, len(indexes)),
            np.repeat(cap, len(indexes)),
            total=float(cluster_total),
        )
    result = pd.Series(weights, index=tickers, dtype=float)
    observed = {
        cluster_id: float(result.iloc[indexes].sum())
        for cluster_id, indexes in members.items()
    }
    if max(observed.values()) > float(cluster_max_weight) + 1e-10:
        raise NdxCompetitionError("cluster weight projection violates its cap")
    return result


def _selected_basket_realized_vol_series(
    grid: pd.DatetimeIndex,
    selections: Iterable[Mapping[str, Any]],
    series: Mapping[str, pd.DataFrame],
    *,
    vol_window: int,
    cache: dict | None = None,
) -> tuple[np.ndarray, dict]:
    """Estimate each active basket's volatility from prices strictly before day t."""
    ordered = sorted(
        [dict(selection) for selection in selections],
        key=lambda item: str(item.get("date") or ""),
    )
    if not ordered or str(ordered[0].get("date")) > grid[0].strftime("%Y-%m-%d"):
        raise NdxCompetitionError("defense signal has no selection at the window start")
    realized_cache: dict[tuple, pd.Series] = cache if cache is not None else {}

    def realized_for(selection: Mapping[str, Any]) -> pd.Series:
        weights = {
            str(ticker).upper(): float(weight)
            for ticker, weight in (selection.get("weights") or {}).items()
        }
        if not weights or not np.isclose(sum(weights.values()), 1.0, atol=1e-8):
            raise NdxCompetitionError("defense signal selection weights are invalid")
        key = (
            int(vol_window),
            tuple(sorted((ticker, round(weight, 14)) for ticker, weight in weights.items())),
        )
        cached = realized_cache.get(key)
        if cached is not None:
            return cached
        close_columns = {}
        for ticker in sorted(weights):
            frame = series.get(ticker)
            if frame is None or "Close" not in frame:
                raise NdxCompetitionError(
                    f"defense signal price history is missing for {ticker}"
                )
            close_columns[ticker] = frame["Close"].astype(float)
        prices = pd.concat(close_columns, axis=1).sort_index().ffill().dropna(how="any")
        returns = prices.pct_change(fill_method=None).dropna(how="any")
        portfolio_returns = returns.mul(pd.Series(weights), axis=1).sum(axis=1)
        realized = portfolio_returns.rolling(
            int(vol_window), min_periods=int(vol_window)
        ).std() * np.sqrt(252.0)
        realized_cache[key] = realized
        return realized

    values = np.empty(len(grid), dtype=float)
    signal_dates = []
    selection_index = 0
    active = ordered[0]
    for index, date in enumerate(grid):
        date_label = date.strftime("%Y-%m-%d")
        while (
            selection_index + 1 < len(ordered)
            and str(ordered[selection_index + 1].get("date")) <= date_label
        ):
            selection_index += 1
            active = ordered[selection_index]
        realized = realized_for(active)
        available = realized.loc[realized.index < date].dropna()
        if available.empty:
            raise NdxCompetitionError(
                f"defense signal lacks {vol_window} prior observations at {date_label}"
            )
        values[index] = float(available.iloc[-1])
        signal_dates.append(pd.Timestamp(available.index[-1]))
    strict = all(signal_date < date for signal_date, date in zip(signal_dates, grid))
    if not strict or not np.isfinite(values).all() or (values <= 0).any():
        raise NdxCompetitionError("defense signal failed strict point-in-time audit")
    return values, {
        "signal": "selected_basket_ex_ante_vol",
        "vol_window": int(vol_window),
        "prehistory_seeded": True,
        "strict_asof_passed": True,
        "first_signal_date": signal_dates[0].strftime("%Y-%m-%d"),
        "last_signal_date": signal_dates[-1].strftime("%Y-%m-%d"),
        "min_realized_vol": float(np.min(values)),
        "max_realized_vol": float(np.max(values)),
    }


def _safe_weights_from_realized_vol(
    realized_vol: np.ndarray,
    *,
    target_vol: float,
    base_weight: float,
    band: float,
) -> np.ndarray:
    lower = max(0.0, float(base_weight) - float(band))
    upper = min(1.0, float(base_weight) + float(band))
    risky_weight = np.clip(float(target_vol) / realized_vol, 0.0, 1.0)
    return np.clip(1.0 - risky_weight, lower, upper)


def _selected_basket_current_drawdown_series(
    grid: pd.DatetimeIndex,
    selections: Iterable[Mapping[str, Any]],
    series: Mapping[str, pd.DataFrame],
    *,
    lookback_days: int,
    cache: dict | None = None,
) -> tuple[np.ndarray, dict]:
    ordered = sorted(
        [dict(selection) for selection in selections],
        key=lambda item: str(item.get("date") or ""),
    )
    if not ordered or str(ordered[0].get("date")) > grid[0].strftime("%Y-%m-%d"):
        raise NdxCompetitionError("drawdown signal has no selection at window start")
    metric_cache: dict[tuple, pd.Series] = cache if cache is not None else {}

    def drawdown_for(selection: Mapping[str, Any]) -> pd.Series:
        weights = {
            str(ticker).upper(): float(weight)
            for ticker, weight in (selection.get("weights") or {}).items()
        }
        if not weights or not np.isclose(sum(weights.values()), 1.0, atol=1e-8):
            raise NdxCompetitionError("drawdown signal selection weights are invalid")
        key = (
            "current_drawdown",
            int(lookback_days),
            tuple(sorted((ticker, round(weight, 14)) for ticker, weight in weights.items())),
        )
        cached = metric_cache.get(key)
        if cached is not None:
            return cached
        prices = pd.concat(
            {
                ticker: series[ticker]["Close"].astype(float)
                for ticker in sorted(weights)
                if ticker in series and "Close" in series[ticker]
            },
            axis=1,
        ).sort_index().ffill().dropna(how="any")
        if len(prices.columns) != len(weights):
            raise NdxCompetitionError("drawdown signal price history is incomplete")
        returns = prices.pct_change(fill_method=None).dropna(how="any")
        portfolio_returns = returns.mul(pd.Series(weights), axis=1).sum(axis=1)
        wealth = (1.0 + portfolio_returns).cumprod()
        trailing_peak = wealth.rolling(
            int(lookback_days), min_periods=int(lookback_days)
        ).max()
        current_drawdown = (1.0 - wealth / trailing_peak).clip(lower=0.0)
        metric_cache[key] = current_drawdown
        return current_drawdown

    values = np.empty(len(grid), dtype=float)
    signal_dates = []
    pointer = 0
    active = ordered[0]
    for index, date in enumerate(grid):
        label = date.strftime("%Y-%m-%d")
        while pointer + 1 < len(ordered) and str(ordered[pointer + 1]["date"]) <= label:
            pointer += 1
            active = ordered[pointer]
        drawdown = drawdown_for(active)
        available = drawdown.loc[drawdown.index < date].dropna()
        if available.empty:
            raise NdxCompetitionError(
                f"drawdown signal lacks {lookback_days} prior observations at {label}"
            )
        values[index] = float(available.iloc[-1])
        signal_dates.append(pd.Timestamp(available.index[-1]))
    strict = all(signal_date < date for signal_date, date in zip(signal_dates, grid))
    if not strict or not np.isfinite(values).all() or (values < 0).any():
        raise NdxCompetitionError("drawdown signal failed strict point-in-time audit")
    return values, {
        "signal": "selected_basket_ex_ante_drawdown",
        "lookback_days": int(lookback_days),
        "prehistory_seeded": True,
        "strict_asof_passed": True,
        "first_signal_date": signal_dates[0].strftime("%Y-%m-%d"),
        "last_signal_date": signal_dates[-1].strftime("%Y-%m-%d"),
        "min_current_drawdown": float(np.min(values)),
        "max_current_drawdown": float(np.max(values)),
    }


def _safe_weights_from_drawdown(
    current_drawdown: np.ndarray,
    *,
    base_weight: float,
    max_safe_weight: float,
    trigger: float,
    full: float,
) -> np.ndarray:
    severity = np.clip(
        (current_drawdown - float(trigger)) / (float(full) - float(trigger)),
        0.0,
        1.0,
    )
    return float(base_weight) + severity * (
        float(max_safe_weight) - float(base_weight)
    )


def _slow_release_safe_weights(raw_weights: np.ndarray, release_step: float) -> np.ndarray:
    """Allow immediate defense increases but cap each day's risk-on release."""
    raw = np.asarray(raw_weights, dtype=float)
    adjusted = raw.copy()
    for index in range(1, len(adjusted)):
        if raw[index] < adjusted[index - 1]:
            adjusted[index] = max(
                raw[index], adjusted[index - 1] - float(release_step)
            )
    return adjusted


def _apply_defense_profile(
    grid: pd.DatetimeIndex,
    risk_nav: np.ndarray,
    risk_equity: np.ndarray,
    flows: list[tuple[int, float]],
    selections: Iterable[Mapping[str, Any]],
    series: Mapping[str, pd.DataFrame],
    profile: Mapping[str, Any],
    *,
    safe_annual: float,
    rebal_days: int,
    rebal_band: float,
    trade_cost_bps: float,
    defense_signal_cache: dict | None = None,
) -> dict:
    safe_weight = float(profile["safe_weight"])
    safe_execution: dict[str, float] = {}
    defense_signal_meta = None
    if profile["defense_mode"] in {"vol_target", "drawdown_guard"}:
        if profile["defense_mode"] == "drawdown_guard":
            current_drawdown, defense_signal_meta = (
                _selected_basket_current_drawdown_series(
                    grid,
                    selections,
                    series,
                    lookback_days=int(profile["defense_drawdown_lookback_days"]),
                    cache=defense_signal_cache,
                )
            )
            safe_weights_series = _safe_weights_from_drawdown(
                current_drawdown,
                base_weight=safe_weight,
                max_safe_weight=float(profile["defense_max_safe_weight"]),
                trigger=float(profile["defense_drawdown_trigger"]),
                full=float(profile["defense_drawdown_full"]),
            )
        elif profile["defense_signal"] == "selected_basket_ex_ante_vol":
            realized_vol, defense_signal_meta = _selected_basket_realized_vol_series(
                grid,
                selections,
                series,
                vol_window=int(profile["defense_vol_window"]),
                cache=defense_signal_cache,
            )
            safe_weights_series = _safe_weights_from_realized_vol(
                realized_vol,
                target_vol=float(profile["target_vol"]),
                base_weight=safe_weight,
                band=float(profile["defense_band"]),
            )
        else:
            safe_weights_series = _vol_target_weight_series(
                risk_nav,
                float(profile["target_vol"]),
                safe_weight,
                float(profile["defense_band"]),
                int(profile["defense_vol_window"]),
            )
            defense_signal_meta = {
                "signal": "risk_nav_since_start",
                "vol_window": int(profile["defense_vol_window"]),
                "prehistory_seeded": False,
                "strict_asof_passed": True,
                "first_signal_date": None,
                "last_signal_date": None,
            }
        raw_safe_weights_series = safe_weights_series.copy()
        if profile.get("defense_release_step") is not None:
            safe_weights_series = _slow_release_safe_weights(
                safe_weights_series,
                float(profile["defense_release_step"]),
            )
        if (
            not np.isfinite(safe_weights_series).all()
            or float(np.min(safe_weights_series)) < 0.0
            or float(np.max(safe_weights_series)) > 1.0
        ):
            raise NdxCompetitionError(
                f"{profile.get('profile_id')}: dynamic safe weights exceed [0, 1]"
            )
        nav, equity, _, safe_turnover, safe_rebalances = _run_defensive_fund(
            grid,
            risk_nav,
            flows,
            float(safe_annual),
            safe_weight,
            0,
            float(profile["defense_exec_band"]),
            w_safe_series=safe_weights_series,
            trade_cost_bps=float(trade_cost_bps),
            execution_stats=safe_execution,
        )
    elif safe_weight > 0:
        safe_weights_series = np.repeat(safe_weight, len(grid)).astype(float)
        raw_safe_weights_series = safe_weights_series.copy()
        nav, equity, _, safe_turnover, safe_rebalances = _run_defensive_fund(
            grid,
            risk_nav,
            flows,
            float(safe_annual),
            safe_weight,
            int(rebal_days),
            float(rebal_band),
            trade_cost_bps=(
                float(trade_cost_bps) if profile.get("explicit_profile") else 0.0
            ),
            execution_stats=safe_execution,
        )
    else:
        safe_weights_series = np.zeros(len(grid), dtype=float)
        raw_safe_weights_series = safe_weights_series.copy()
        nav, equity = risk_nav, risk_equity
        safe_turnover, safe_rebalances = 0.0, 0
    return {
        "nav": nav,
        "equity": equity,
        "safe_weight_series": safe_weights_series,
        "raw_safe_weight_series": raw_safe_weights_series,
        "actual_safe_weight_series": np.asarray(
            safe_execution.get("actual_safe_weight_series", np.zeros(len(grid))),
            dtype=float,
        ),
        "safe_turnover": float(safe_turnover),
        "safe_rebalances": int(safe_rebalances),
        "safe_cost_paid": float(safe_execution.get("cost_paid") or 0.0),
        "avg_safe_weight": (
            float(np.mean(safe_weights_series[1:]))
            if len(safe_weights_series) > 1 else float(safe_weights_series[0])
        ),
        "min_safe_weight": float(np.min(safe_weights_series)),
        "max_safe_weight": float(np.max(safe_weights_series)),
        "defense_signal_meta": defense_signal_meta,
    }


def _risk_parity_weights(
    returns: pd.DataFrame,
    *,
    max_weight: float = 0.35,
    min_weight: float = 0.02,
) -> dict[str, float]:
    tickers = list(returns.columns)
    n = len(tickers)
    if n < 2 or len(returns) < 60:
        raise NdxCompetitionError("risk parity requires at least 60 common return rows")
    cov = returns.cov().to_numpy(dtype=float) * 252.0
    diagonal = np.diag(np.diag(cov))
    cov = cov * 0.90 + diagonal * 0.10
    scale = max(float(np.trace(cov)) / n, 1e-8)
    cov = cov + np.eye(n) * scale * 1e-6
    if not np.isfinite(cov).all():
        raise NdxCompetitionError("risk parity covariance is not finite")

    floor = min(max(0.0, float(min_weight)), 1.0 / n)
    cap = max(float(max_weight), 1.0 / n)

    def objective(weights):
        portfolio_variance = float(weights @ cov @ weights)
        if portfolio_variance <= 0 or not np.isfinite(portfolio_variance):
            return 1e6
        contribution = weights * (cov @ weights) / portfolio_variance
        return float(np.sum((contribution - 1.0 / n) ** 2))

    result = minimize(
        objective,
        np.repeat(1.0 / n, n),
        method="SLSQP",
        bounds=[(floor, cap)] * n,
        constraints=[{"type": "eq", "fun": lambda weights: float(weights.sum() - 1.0)}],
        options={"maxiter": 500, "ftol": 1e-12, "disp": False},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise NdxCompetitionError(f"risk parity optimization failed: {result.message}")
    weights = pd.Series(result.x, index=tickers, dtype=float)
    weights /= float(weights.sum())
    return {ticker: float(weights[ticker]) for ticker in tickers}


def _choice_weights(
    tickers: list[str],
    metrics: pd.DataFrame,
    *,
    weight_mode: str,
    source_weights: Mapping[str, float],
    series: Mapping[str, pd.DataFrame],
    asof: pd.Timestamp,
    lookback_days: int,
    max_weight: float,
    min_weight: float,
    cluster_labels: Mapping[str, int] | None = None,
    cluster_max_weight: float | None = None,
    top_weight_count: int | None = None,
    top_weight_cap: float | None = None,
    min_effective_n: float | None = None,
    sic_classifications: pd.DataFrame | None = None,
    sic4_max_weight: float | None = None,
    sic2_max_weight: float | None = None,
) -> dict[str, float]:
    if weight_mode == "equal":
        raw = pd.Series(1.0, index=tickers, dtype=float)
    elif weight_mode == "score_risk":
        raw = pd.Series(_weights_for(tickers, metrics, "score_risk"), dtype=float)
    elif weight_mode == "inverse_vol":
        vol = pd.to_numeric(metrics.reindex(tickers)["vol_3y"], errors="coerce")
        if vol.isna().any() or (vol <= 0).any():
            raise NdxCompetitionError("inverse-vol weights require positive volatility")
        raw = 1.0 / vol
    elif weight_mode == "source_weight":
        raw = pd.Series({ticker: float(source_weights.get(ticker, 0.0)) for ticker in tickers})
        if not np.isfinite(raw.to_numpy(dtype=float)).all() or (raw <= 0).any():
            raise NdxCompetitionError("source weights missing for selected ticker")
    elif weight_mode == "risk_parity":
        returns = _returns_before(series, tickers, asof, lookback_days)
        risk_weights = _risk_parity_weights(
            returns,
            max_weight=float(max_weight),
            min_weight=float(min_weight),
        )
        raw = pd.Series(risk_weights, dtype=float).reindex(tickers)
    else:
        raise NdxCompetitionError(f"unsupported weight mode: {weight_mode}")
    if top_weight_count is not None or top_weight_cap is not None:
        if weight_mode != "source_weight":
            raise NdxCompetitionError(
                "concentration-envelope projection requires source_weight"
            )
        if top_weight_count is None or top_weight_cap is None:
            raise NdxCompetitionError(
                "top-weight count and cap must be declared together"
            )
        if (
            cluster_max_weight is not None
            or sic4_max_weight is not None
            or sic2_max_weight is not None
        ):
            raise NdxCompetitionError(
                "concentration envelope cannot be combined with cluster or SIC caps"
            )
        try:
            bounded = project_concentration_envelope_weights(
                raw,
                max_weight=float(max_weight),
                min_weight=float(min_weight),
                top_weight_count=int(top_weight_count),
                top_weight_cap=float(top_weight_cap),
                min_effective_n=min_effective_n,
            )
        except WeightConstraintError as exc:
            raise NdxCompetitionError(
                f"concentration-envelope allocation failed: {exc}"
            ) from exc
    elif sic4_max_weight is not None or sic2_max_weight is not None:
        if sic_classifications is None:
            raise NdxCompetitionError("SIC weight caps require classifications")
        try:
            bounded = sic_capped_weights(
                raw,
                sic_classifications,
                max_weight=float(max_weight),
                min_weight=float(min_weight),
                max_weight_sic4=sic4_max_weight,
                max_weight_sic2=sic2_max_weight,
            )
        except Exception as exc:
            raise NdxCompetitionError(f"SIC weight allocation failed: {exc}") from exc
    elif cluster_max_weight is not None:
        if cluster_labels is None:
            raise NdxCompetitionError("cluster cap requires point-in-time cluster labels")
        bounded = _cluster_capped_weights(
            raw,
            cluster_labels,
            cluster_max_weight=float(cluster_max_weight),
            max_weight=float(max_weight),
            min_weight=float(min_weight),
        )
    else:
        bounded = _capped_weights(
            raw,
            max_weight=float(max_weight),
            min_weight=float(min_weight),
        )
    return {ticker: float(bounded[ticker]) for ticker in tickers}


def _choose_from_snapshot(
    snapshot: pd.DataFrame,
    membership_evidence: dict,
    *,
    asof: pd.Timestamp,
    series: Mapping[str, pd.DataFrame],
    top_n: int,
    weight_mode: str,
    lookback_days: int,
    min_history_days: int,
    max_weight: float = 0.35,
    min_weight: float = 0.02,
    selection_mode: str = DEFAULT_SELECTION_MODE,
    correlation_lookback_days: int = DEFAULT_CORRELATION_LOOKBACK_DAYS,
    correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    correlation_pool_size: int = 0,
    max_names_per_cluster: int = 1,
    cluster_max_weight: float | None = None,
    top_weight_count: int | None = None,
    top_weight_cap: float | None = None,
    min_effective_n: float | None = None,
    correlation_cache: dict | None = None,
    quality_scores: pd.DataFrame | None = None,
    fundamental_score_weight: float = 0.0,
    quality_policy_id: str | None = None,
    valuation_scores: pd.DataFrame | None = None,
    valuation_score_weight: float = 0.0,
    valuation_policy_id: str | None = None,
    quality_selection_mode: str = DEFAULT_QUALITY_SELECTION_MODE,
    quality_challenge_pool_size: int | None = None,
    max_quality_replacements: int = 0,
    max_names_per_sic4: int | None = None,
    max_names_per_sic2: int | None = None,
    sic4_max_weight: float | None = None,
    sic2_max_weight: float | None = None,
    candidate_tickers: str | Iterable[str] | None = None,
) -> NdxChoice:
    expected = sorted(snapshot["ticker"].astype(str).str.upper().unique())
    missing_price = []
    stale_price = []
    available = []
    asof_date = pd.Timestamp(asof)
    for ticker in expected:
        frame = series.get(ticker)
        if frame is None or "Close" not in frame:
            missing_price.append(ticker)
            continue
        history = frame["Close"][frame.index < asof_date].dropna()
        if history.empty:
            missing_price.append(ticker)
            continue
        age_days = int((asof_date.normalize() - history.index[-1].normalize()).days)
        if age_days > MAX_PRICE_AGE_CALENDAR_DAYS:
            stale_price.append(ticker)
            continue
        available.append(ticker)
    price_coverage = len(available) / len(expected) if expected else 0.0
    if price_coverage < MIN_UNIVERSE_PRICE_COVERAGE:
        raise NdxCompetitionError(
            f"point-in-time universe price coverage {price_coverage:.1%} < "
            f"{MIN_UNIVERSE_PRICE_COVERAGE:.0%}; missing={missing_price}; "
            f"stale={stale_price}"
        )
    subset = {ticker: series[ticker] for ticker in available}
    metrics = _metrics_asof(
        subset,
        asof_date,
        lookback_days=int(lookback_days),
        min_history_days=max(int(min_history_days), int(lookback_days) + 1),
    )
    quality_selection_mode = str(
        quality_selection_mode or DEFAULT_QUALITY_SELECTION_MODE
    ).strip().lower()
    if quality_selection_mode not in SUPPORTED_QUALITY_SELECTION_MODES:
        raise NdxCompetitionError(
            f"unsupported quality selection mode {quality_selection_mode!r}"
        )
    quality_challenge_required = (
        quality_selection_mode == "bounded_challenge"
    )
    if quality_challenge_required:
        if (
            float(fundamental_score_weight) != 0.0
            or float(valuation_score_weight) != 0.0
        ):
            raise NdxCompetitionError(
                "bounded quality challenge cannot be combined with score blends"
            )
        if str(selection_mode or DEFAULT_SELECTION_MODE).lower() != "rank":
            raise NdxCompetitionError(
                "bounded quality challenge requires rank selection"
            )
        if (
            quality_challenge_pool_size is None
            or int(quality_challenge_pool_size) <= int(top_n)
        ):
            raise NdxCompetitionError(
                "quality challenge pool must be larger than the price baseline"
            )
        if not 1 <= int(max_quality_replacements) <= min(
            int(top_n), int(quality_challenge_pool_size) - int(top_n)
        ):
            raise NdxCompetitionError("invalid quality replacement budget")
        if max_names_per_sic4 is not None or max_names_per_sic2 is not None:
            raise NdxCompetitionError(
                "bounded quality challenge cannot be combined with SIC name replacement"
            )
    quality_required = bool(
        float(fundamental_score_weight) > 0
        or quality_policy_id is not None
        or quality_challenge_required
        or max_names_per_sic4 is not None
        or max_names_per_sic2 is not None
        or sic4_max_weight is not None
        or sic2_max_weight is not None
    )
    quality_frame = None
    quality_score_coverage = None
    quality_score_date = None
    quality_future_data_guard_passed = None
    eligible_quality = None
    if quality_required:
        if quality_scores is None:
            raise NdxCompetitionError("quality/SIC profile has no score evidence")
        if str(quality_policy_id or "") != QUALITY_POLICY_ID:
            raise NdxCompetitionError("quality policy identity changed")
        try:
            quality_frame = quality_snapshot(quality_scores, asof_date)
        except Exception as exc:
            raise NdxCompetitionError(f"quality snapshot failed: {exc}") from exc
        expected_quality = quality_frame.reindex(expected)
        if expected_quality[["sic", "sic_group_2d"]].isna().any().any():
            missing_sic = expected_quality.index[
                expected_quality["sic"].isna()
                | expected_quality["sic_group_2d"].isna()
            ].tolist()
            raise NdxCompetitionError(
                f"point-in-time SIC coverage incomplete: {missing_sic}"
            )
        quality_score_date = asof_date.strftime("%Y-%m-%d")
        quality_future_data_guard_passed = bool(
            set(quality_frame["selection_date"].astype(str))
            == {quality_score_date}
        )
        if not quality_future_data_guard_passed:
            raise NdxCompetitionError("quality score date is not strict as-of")
    valuation_required = bool(float(valuation_score_weight) > 0)
    valuation_frame = None
    valuation_score_coverage = None
    valuation_observed_coverage = None
    valuation_score_date = None
    valuation_future_data_guard_passed = None
    valuation_missing_neutral_count = 0
    if valuation_required:
        if valuation_scores is None:
            raise NdxCompetitionError("valuation profile has no score evidence")
        if str(valuation_policy_id or "") not in SUPPORTED_VALUATION_SCORE_POLICY_IDS:
            raise NdxCompetitionError("valuation policy identity changed")
        try:
            valuation_frame = valuation_snapshot(
                valuation_scores,
                asof_date,
                policy_id=str(valuation_policy_id),
            )
        except Exception as exc:
            raise NdxCompetitionError(f"valuation snapshot failed: {exc}") from exc
        expected_valuation = valuation_frame.reindex(expected)
        valuation_values = pd.to_numeric(
            expected_valuation["valuation_score"], errors="coerce"
        )
        valuation_score_coverage = (
            float(valuation_values.notna().mean()) if expected else 0.0
        )
        if valuation_score_coverage < MIN_UNIVERSE_SCORE_COVERAGE:
            missing_valuation = expected_valuation.index[
                valuation_values.isna()
            ].tolist()
            raise NdxCompetitionError(
                f"point-in-time valuation coverage {valuation_score_coverage:.1%} < "
                f"{MIN_UNIVERSE_SCORE_COVERAGE:.0%}; missing={missing_valuation}"
            )
        missing_neutral = expected_valuation[
            "valuation_missing_neutral_applied"
        ].fillna(False).astype(bool)
        valuation_missing_neutral_count = int(missing_neutral.sum())
        valuation_observed_coverage = (
            1.0 - valuation_missing_neutral_count / len(expected)
            if expected else 0.0
        )
        valuation_score_date = asof_date.strftime("%Y-%m-%d")
        valuation_future_data_guard_passed = bool(
            set(valuation_frame["selection_date"].astype(str))
            == {valuation_score_date}
        )
        if not valuation_future_data_guard_passed:
            raise NdxCompetitionError("valuation score date is not strict as-of")
    metrics["price_score_percentile"] = metrics["attack_score"].rank(
        method="average", pct=True
    )
    quality_score_required = bool(
        float(fundamental_score_weight) > 0 or quality_challenge_required
    )
    if quality_score_required:
        eligible_quality = quality_frame[
            quality_frame["quality_eligible"].eq(True)
            & pd.to_numeric(
                quality_frame["quality_score"], errors="coerce"
            ).notna()
        ]
        quality_score_coverage = (
            len(set(expected) & set(eligible_quality.index)) / len(expected)
            if expected else 0.0
        )
        if quality_score_coverage < MIN_UNIVERSE_SCORE_COVERAGE:
            raise NdxCompetitionError(
                f"point-in-time quality coverage {quality_score_coverage:.1%} < "
                f"{MIN_UNIVERSE_SCORE_COVERAGE:.0%}"
            )
    quality_weight = float(fundamental_score_weight)
    valuation_weight = float(valuation_score_weight)
    if quality_weight + valuation_weight > 1.0:
        raise NdxCompetitionError("quality plus valuation score weights exceed 1")
    if quality_weight > 0:
        metrics = metrics.join(eligible_quality[["quality_score"]], how="inner")
    if valuation_weight > 0:
        metrics = metrics.join(
            valuation_frame[["valuation_score"]],
            how="inner",
        )
    if quality_weight > 0 or valuation_weight > 0:
        metrics["combined_score"] = (
            (1.0 - quality_weight - valuation_weight)
            * metrics["price_score_percentile"]
        )
        if quality_weight > 0:
            metrics["combined_score"] += (
                quality_weight
                * pd.to_numeric(metrics["quality_score"], errors="coerce")
                / 100.0
            )
        if valuation_weight > 0:
            metrics["combined_score"] += (
                valuation_weight
                * pd.to_numeric(metrics["valuation_score"], errors="coerce")
                / 100.0
            )
    else:
        metrics["combined_score"] = metrics["attack_score"]
    scored = sorted(metrics.index.tolist()) if not metrics.empty else []
    unscored = sorted(set(expected) - set(scored))
    score_coverage = len(scored) / len(expected) if expected else 0.0
    if score_coverage < MIN_UNIVERSE_SCORE_COVERAGE or len(scored) < int(top_n):
        raise NdxCompetitionError(
            f"point-in-time universe score coverage {score_coverage:.1%} < "
            f"{MIN_UNIVERSE_SCORE_COVERAGE:.0%}; unscored={unscored}"
        )
    ranked = metrics.reset_index(drop=True).sort_values(
        ["combined_score", "attack_score", "ret_3y", "ticker"],
        ascending=[False, False, False, True],
        kind="stable",
    )["ticker"].tolist()
    distinct_ranked = []
    seen_issuers = set()
    duplicate_issuer_tickers = []
    for ticker in ranked:
        issuer = _issuer_key(ticker)
        if issuer in seen_issuers:
            duplicate_issuer_tickers.append(ticker)
            continue
        seen_issuers.add(issuer)
        distinct_ranked.append(ticker)
    frozen_candidates = _parse_candidate_tickers(candidate_tickers)
    candidate_member_count = None
    if frozen_candidates:
        allowed = set(frozen_candidates)
        candidate_member_count = len(set(expected) & allowed)
        distinct_ranked = [ticker for ticker in distinct_ranked if ticker in allowed]
    if len(distinct_ranked) < int(top_n):
        raise NdxCompetitionError(
            f"only {len(distinct_ranked)} distinct issuers available for top{int(top_n)}"
            + (
                f" after frozen candidate-pool intersection ({candidate_member_count} members)"
                if frozen_candidates else ""
            )
        )
    selection_mode = str(selection_mode or DEFAULT_SELECTION_MODE).lower()
    correlation_required = (
        selection_mode != DEFAULT_SELECTION_MODE or cluster_max_weight is not None
    )
    corr = None
    corr_meta = None
    cluster_labels = None
    rejected_correlated = []
    rejected_sic: dict[str, str] = {}
    quality_challenge_pool: list[str] = []
    quality_replacements: list[dict[str, Any]] = []
    if selection_mode == DEFAULT_SELECTION_MODE:
        if quality_challenge_required:
            picked, quality_challenge_pool, quality_replacements = (
                _select_bounded_quality_challengers(
                    distinct_ranked,
                    quality_frame,
                    top_n=int(top_n),
                    pool_size=int(quality_challenge_pool_size),
                    max_replacements=int(max_quality_replacements),
                )
            )
        elif max_names_per_sic4 is not None or max_names_per_sic2 is not None:
            picked, rejected_sic = _select_ranked_with_sic_caps(
                distinct_ranked,
                quality_frame,
                top_n=int(top_n),
                max_names_per_sic4=max_names_per_sic4,
                max_names_per_sic2=max_names_per_sic2,
            )
        else:
            picked = distinct_ranked[:int(top_n)]
        if correlation_required:
            corr, corr_meta = _correlation_before(
                series,
                picked,
                asof_date,
                lookback_days=int(correlation_lookback_days),
                cache=correlation_cache,
            )
            cluster_labels = _complete_linkage_clusters(
                corr, float(correlation_threshold)
            )
    else:
        pool_count = int(correlation_pool_size or len(distinct_ranked))
        pool = distinct_ranked[:pool_count]
        if len(pool) < int(top_n):
            raise NdxCompetitionError(
                f"correlation pool has only {len(pool)} names for top{int(top_n)}"
            )
        corr, corr_meta = _correlation_before(
            series,
            pool,
            asof_date,
            lookback_days=int(correlation_lookback_days),
            cache=correlation_cache,
        )
        picked, cluster_labels, rejected_correlated = _select_with_correlation(
            pool,
            corr,
            top_n=int(top_n),
            selection_mode=selection_mode,
            threshold=float(correlation_threshold),
            max_names_per_cluster=int(max_names_per_cluster),
        )
        corr = corr.loc[picked, picked]
    if len(picked) != int(top_n):
        raise NdxCompetitionError(
            f"selection produced {len(picked)} names instead of top{int(top_n)}"
        )
    source_weight_by_issuer = {}
    for row in snapshot.itertuples(index=False):
        ticker = str(row.ticker).upper()
        issuer = _issuer_key(ticker)
        value = float(row.weight)
        if not np.isfinite(value) or value <= 0:
            continue
        source_weight_by_issuer[issuer] = (
            source_weight_by_issuer.get(issuer, 0.0) + value
        )
    source_weights = {
        ticker: source_weight_by_issuer.get(_issuer_key(ticker), 0.0)
        for ticker in picked
    }
    weights = _choice_weights(
        picked,
        metrics,
        weight_mode=weight_mode,
        source_weights=source_weights,
        series=series,
        asof=pd.Timestamp(asof),
        lookback_days=int(lookback_days),
        max_weight=float(max_weight),
        min_weight=float(min_weight),
        cluster_labels=cluster_labels,
        cluster_max_weight=cluster_max_weight,
        top_weight_count=top_weight_count,
        top_weight_cap=top_weight_cap,
        min_effective_n=min_effective_n,
        sic_classifications=(
            quality_frame if quality_required else None
        ),
        sic4_max_weight=sic4_max_weight,
        sic2_max_weight=sic2_max_weight,
    )
    pair_values = [
        float(corr.loc[ticker_a, ticker_b])
        for index, ticker_a in enumerate(picked)
        for ticker_b in picked[index + 1:]
    ] if corr is not None else []
    cluster_weights = None
    if cluster_labels is not None:
        cluster_weights = {}
        for ticker, weight in weights.items():
            cluster_id = int(cluster_labels[ticker])
            cluster_weights[cluster_id] = (
                cluster_weights.get(cluster_id, 0.0) + float(weight)
            )
    sic4_by_ticker = None
    sic2_by_ticker = None
    sic4_weights = None
    sic2_weights = None
    if quality_required:
        selected_classes = quality_frame.reindex(picked)
        sic4_by_ticker = {
            ticker: int(selected_classes.loc[ticker, "sic"])
            for ticker in picked
        }
        sic2_by_ticker = {
            ticker: str(selected_classes.loc[ticker, "sic_group_2d"])
            for ticker in picked
        }
        sic4_weights = {}
        sic2_weights = {}
        for ticker, weight in weights.items():
            sic4 = sic4_by_ticker[ticker]
            sic2 = sic2_by_ticker[ticker]
            sic4_weights[sic4] = sic4_weights.get(sic4, 0.0) + float(weight)
            sic2_weights[sic2] = sic2_weights.get(sic2, 0.0) + float(weight)
    return NdxChoice(
        mode=f"top{int(top_n)}_{weight_mode}_{selection_mode}",
        top_n=int(top_n),
        weight_mode=weight_mode,
        tickers=tuple(picked),
        weights=weights,
        selection_date=pd.Timestamp(asof).strftime("%Y-%m-%d"),
        membership_evidence=dict(membership_evidence),
        expected_count=len(expected),
        expected_issuer_count=len({_issuer_key(ticker) for ticker in expected}),
        price_count=len(available),
        scored_count=len(scored),
        price_coverage=float(price_coverage),
        score_coverage=float(score_coverage),
        missing_price_tickers=tuple(missing_price),
        stale_price_tickers=tuple(stale_price),
        unscored_tickers=tuple(unscored),
        duplicate_issuer_tickers=tuple(duplicate_issuer_tickers),
        selection_mode=selection_mode,
        correlation_lookback_days=(
            int(correlation_lookback_days) if correlation_required else None
        ),
        correlation_threshold=(
            float(correlation_threshold) if correlation_required else None
        ),
        correlation_observations=(
            int(corr_meta["observations"]) if corr_meta is not None else None
        ),
        correlation_price_start=(
            corr_meta["price_start"] if corr_meta is not None else None
        ),
        correlation_price_end=(
            corr_meta["price_end"] if corr_meta is not None else None
        ),
        correlation_strict_asof_passed=(
            bool(corr_meta["strict_asof_passed"]) if corr_meta is not None else None
        ),
        correlation_pool_size=(
            int(correlation_pool_size or len(distinct_ranked))
            if selection_mode != DEFAULT_SELECTION_MODE
            else int(top_n) if correlation_required else None
        ),
        max_names_per_cluster=(
            int(max_names_per_cluster) if correlation_required else None
        ),
        cluster_max_weight=(
            float(cluster_max_weight) if cluster_max_weight is not None else None
        ),
        top_weight_count=(
            int(top_weight_count) if top_weight_count is not None else None
        ),
        top_weight_cap=(
            float(top_weight_cap) if top_weight_cap is not None else None
        ),
        min_effective_n=(
            float(min_effective_n) if min_effective_n is not None else None
        ),
        cluster_labels=(
            {ticker: int(cluster_labels[ticker]) for ticker in picked}
            if cluster_labels is not None else None
        ),
        cluster_weights=cluster_weights,
        max_pair_correlation=max(pair_values) if pair_values else None,
        rejected_correlated_tickers=tuple(rejected_correlated),
        fundamental_score_weight=float(fundamental_score_weight),
        quality_policy_id=quality_policy_id if quality_required else None,
        quality_score_coverage=quality_score_coverage,
        quality_score_date=quality_score_date,
        quality_future_data_guard_passed=quality_future_data_guard_passed,
        quality_selection_mode=quality_selection_mode,
        quality_challenge_pool_size=(
            int(quality_challenge_pool_size)
            if quality_challenge_required else None
        ),
        max_quality_replacements=(
            int(max_quality_replacements) if quality_challenge_required else 0
        ),
        quality_challenge_pool_tickers=tuple(quality_challenge_pool),
        quality_replacement_pairs=tuple(quality_replacements),
        valuation_score_weight=float(valuation_score_weight),
        valuation_policy_id=(
            valuation_policy_id if valuation_required else None
        ),
        valuation_score_coverage=valuation_score_coverage,
        valuation_observed_coverage=valuation_observed_coverage,
        valuation_score_date=valuation_score_date,
        valuation_future_data_guard_passed=(
            valuation_future_data_guard_passed
        ),
        valuation_missing_neutral_count=valuation_missing_neutral_count,
        max_names_per_sic4=max_names_per_sic4,
        max_names_per_sic2=max_names_per_sic2,
        sic4_max_weight=sic4_max_weight,
        sic2_max_weight=sic2_max_weight,
        sic4_by_ticker=sic4_by_ticker,
        sic2_by_ticker=sic2_by_ticker,
        sic4_weights=sic4_weights,
        sic2_weights=sic2_weights,
        rejected_sic_tickers=tuple(rejected_sic),
        rejected_sic_reasons=dict(rejected_sic) if rejected_sic else None,
        candidate_tickers=frozen_candidates,
        candidate_member_count=candidate_member_count,
    )


def _choose_historical(
    history: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    series: Mapping[str, pd.DataFrame],
    top_n: int,
    weight_mode: str,
    lookback_days: int,
    min_history_days: int,
    max_weight: float = 0.35,
    min_weight: float = 0.02,
    selection_mode: str = DEFAULT_SELECTION_MODE,
    correlation_lookback_days: int = DEFAULT_CORRELATION_LOOKBACK_DAYS,
    correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    correlation_pool_size: int = 0,
    max_names_per_cluster: int = 1,
    cluster_max_weight: float | None = None,
    top_weight_count: int | None = None,
    top_weight_cap: float | None = None,
    min_effective_n: float | None = None,
    correlation_cache: dict | None = None,
    quality_scores: pd.DataFrame | None = None,
    fundamental_score_weight: float = 0.0,
    quality_policy_id: str | None = None,
    valuation_scores: pd.DataFrame | None = None,
    valuation_score_weight: float = 0.0,
    valuation_policy_id: str | None = None,
    quality_selection_mode: str = DEFAULT_QUALITY_SELECTION_MODE,
    quality_challenge_pool_size: int | None = None,
    max_quality_replacements: int = 0,
    max_names_per_sic4: int | None = None,
    max_names_per_sic2: int | None = None,
    sic4_max_weight: float | None = None,
    sic2_max_weight: float | None = None,
    candidate_tickers: str | Iterable[str] | None = None,
) -> NdxChoice:
    snapshot, evidence = constituents_asof(history, asof)
    return _choose_from_snapshot(
        snapshot,
        evidence,
        asof=asof,
        series=series,
        top_n=top_n,
        weight_mode=weight_mode,
        lookback_days=lookback_days,
        min_history_days=min_history_days,
        max_weight=max_weight,
        min_weight=min_weight,
        selection_mode=selection_mode,
        correlation_lookback_days=correlation_lookback_days,
        correlation_threshold=correlation_threshold,
        correlation_pool_size=correlation_pool_size,
        max_names_per_cluster=max_names_per_cluster,
        cluster_max_weight=cluster_max_weight,
        top_weight_count=top_weight_count,
        top_weight_cap=top_weight_cap,
        min_effective_n=min_effective_n,
        correlation_cache=correlation_cache,
        quality_scores=quality_scores,
        fundamental_score_weight=fundamental_score_weight,
        quality_policy_id=quality_policy_id,
        valuation_scores=valuation_scores,
        valuation_score_weight=valuation_score_weight,
        valuation_policy_id=valuation_policy_id,
        quality_selection_mode=quality_selection_mode,
        quality_challenge_pool_size=quality_challenge_pool_size,
        max_quality_replacements=max_quality_replacements,
        max_names_per_sic4=max_names_per_sic4,
        max_names_per_sic2=max_names_per_sic2,
        sic4_max_weight=sic4_max_weight,
        sic2_max_weight=sic2_max_weight,
        candidate_tickers=candidate_tickers,
    )


def _active_ndx_risk_leg(
    cfg,
    grid: pd.DatetimeIndex,
    panels: Mapping[str, dict],
    listing_i: Mapping[str, int],
    last_i: Mapping[str, int],
    series: Mapping[str, pd.DataFrame],
    history: pd.DataFrame,
    *,
    top_n: int,
    weight_mode: str,
    total_cap: float,
    monthly: float,
    lookback_days: int,
    min_history_days: int,
    rebalance_months: int,
    trade_cost_bps: float,
    max_weight: float,
    min_weight: float,
    selection_mode: str,
    correlation_lookback_days: int | None,
    correlation_threshold: float | None,
    correlation_pool_size: int | None,
    max_names_per_cluster: int | None,
    cluster_max_weight: float | None,
    top_weight_count: int | None,
    top_weight_cap: float | None,
    min_effective_n: float | None,
    quality_scores: pd.DataFrame | None,
    fundamental_score_weight: float,
    quality_policy_id: str | None,
    valuation_scores: pd.DataFrame | None,
    valuation_score_weight: float,
    valuation_policy_id: str | None,
    quality_selection_mode: str,
    quality_challenge_pool_size: int | None,
    max_quality_replacements: int,
    max_names_per_sic4: int | None,
    max_names_per_sic2: int | None,
    sic4_max_weight: float | None,
    sic2_max_weight: float | None,
    candidate_tickers: tuple[str, ...],
    choice_cache: dict,
    correlation_cache: dict,
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, float]], dict]:
    n = len(grid)
    symbols = {}
    entry_i: dict[str, int] = {}
    units = 0.0
    cash = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    flows: list[tuple[int, float]] = []
    rebalance_set = set(_rebalance_indexes(grid, rebalance_months))
    trade_cost = max(0.0, float(trade_cost_bps)) / 10000.0
    turnover = 0.0
    cost_paid = 0.0
    failed_rebalances = 0
    rebalance_failures = []
    selections = []
    prev_selection: set[str] | None = None

    def choose(index: int) -> NdxChoice:
        key = (
            grid[index].strftime("%Y-%m-%d"), int(top_n), weight_mode,
            int(lookback_days), int(min_history_days), float(max_weight), float(min_weight),
            str(selection_mode), correlation_lookback_days, correlation_threshold,
            correlation_pool_size, max_names_per_cluster, cluster_max_weight,
            top_weight_count, top_weight_cap, min_effective_n,
            float(fundamental_score_weight), quality_policy_id,
            float(valuation_score_weight), valuation_policy_id,
            str(quality_selection_mode), quality_challenge_pool_size,
            int(max_quality_replacements),
            max_names_per_sic4, max_names_per_sic2,
            sic4_max_weight, sic2_max_weight,
            tuple(candidate_tickers),
        )
        cached = choice_cache.get(key)
        if isinstance(cached, Exception):
            raise cached
        if cached is not None:
            return cached
        try:
            choice = _choose_historical(
                history,
                asof=grid[index],
                series=series,
                top_n=int(top_n),
                weight_mode=weight_mode,
                lookback_days=int(lookback_days),
                min_history_days=int(min_history_days),
                max_weight=float(max_weight),
                min_weight=float(min_weight),
                selection_mode=str(selection_mode),
                correlation_lookback_days=int(
                    correlation_lookback_days or DEFAULT_CORRELATION_LOOKBACK_DAYS
                ),
                correlation_threshold=float(
                    correlation_threshold or DEFAULT_CORRELATION_THRESHOLD
                ),
                correlation_pool_size=int(correlation_pool_size or 0),
                max_names_per_cluster=int(max_names_per_cluster or 1),
                cluster_max_weight=cluster_max_weight,
                top_weight_count=top_weight_count,
                top_weight_cap=top_weight_cap,
                min_effective_n=min_effective_n,
                correlation_cache=correlation_cache,
                quality_scores=quality_scores,
                fundamental_score_weight=float(fundamental_score_weight),
                quality_policy_id=quality_policy_id,
                valuation_scores=valuation_scores,
                valuation_score_weight=float(valuation_score_weight),
                valuation_policy_id=valuation_policy_id,
                quality_selection_mode=str(quality_selection_mode),
                quality_challenge_pool_size=quality_challenge_pool_size,
                max_quality_replacements=int(max_quality_replacements),
                max_names_per_sic4=max_names_per_sic4,
                max_names_per_sic2=max_names_per_sic2,
                sic4_max_weight=sic4_max_weight,
                sic2_max_weight=sic2_max_weight,
                candidate_tickers=candidate_tickers,
            )
        except Exception as exc:
            choice_cache[key] = exc
            raise
        choice_cache[key] = choice
        return choice

    def active_symbols(index: int) -> list[str]:
        return [
            ticker for ticker in symbols
            if listing_i.get(ticker, 0) <= index <= last_i.get(ticker, n - 1)
        ]

    def has_stale_holding(index: int) -> bool:
        for ticker in symbols:
            final_index = last_i.get(ticker, n - 1)
            if final_index >= index:
                continue
            age_days = int(
                (grid[index].normalize() - grid[final_index].normalize()).days
            )
            if age_days > MAX_PRICE_AGE_CALENDAR_DAYS:
                return True
        return False

    def rebalance_value(index: int, *, market_only: bool = False) -> float:
        total = 0.0 if market_only else float(cash)
        for ticker, state in symbols.items():
            final_index = last_i.get(ticker, n - 1)
            if final_index < index:
                price = float(panels[ticker]["close"][final_index])
            else:
                price = float(panels[ticker]["open"][index])
            total += state.shares * price
            if not market_only:
                total += state.reserve_cash + getattr(state, "pending_core_cash", 0.0)
        return total

    for i in range(n):
        total_before = _symbols_value_at(symbols, panels, i, "close") if symbols else 0.0
        nav_before = total_before / units if units > 0 else 1.0
        if i == 0:
            units += float(total_cap) / nav_before
            flows.append((i, float(total_cap)))
            cash += float(total_cap)

        emergency_rebalance = has_stale_holding(i)
        if i in rebalance_set or emergency_rebalance:
            try:
                choice = choose(i)
            except Exception as exc:
                failed_rebalances += 1
                rebalance_failures.append({
                    "date": grid[i].strftime("%Y-%m-%d"),
                    "reason": str(exc),
                })
                choice = None
            if choice is not None:
                alive = [
                    ticker for ticker in choice.tickers
                    if ticker in panels and last_i.get(ticker, -1) >= i
                ]
                weight_sum = sum(choice.weights.get(ticker, 0.0) for ticker in alive)
                if len(alive) != choice.top_n or weight_sum <= 0:
                    failed_rebalances += 1
                else:
                    had_symbols = bool(symbols)
                    gross_value = rebalance_value(i)
                    sell_notional = (
                        rebalance_value(i, market_only=True)
                        if had_symbols else 0.0
                    )
                    core_buy = gross_value * float(cfg.portfolio.core_ratio) if had_symbols else 0.0
                    traded = sell_notional + core_buy
                    cost = traded * trade_cost
                    deployable = max(0.0, gross_value - cost)
                    turnover += traded
                    cost_paid += cost
                    symbols = {}
                    entry_i = {}
                    cash = 0.0
                    for ticker in alive:
                        weight = float(choice.weights[ticker]) / weight_sum
                        price = float(panels[ticker]["open"][i])
                        if not np.isfinite(price) or price <= 0:
                            continue
                        symbols[ticker] = eng.init_symbol(
                            ticker, deployable * weight, price, cfg
                        )
                        entry_i[ticker] = i
                    current = set(symbols)
                    selections.append({
                        "date": grid[i].strftime("%Y-%m-%d"),
                        "trigger": "stale_holding" if emergency_rebalance else "scheduled",
                        "report_date": choice.membership_evidence.get("report_date"),
                        "available_date": choice.membership_evidence.get("available_date"),
                        "accession_number": choice.membership_evidence.get("accession_number"),
                        "expected_count": choice.expected_count,
                        "expected_issuer_count": choice.expected_issuer_count,
                        "candidate_member_count": choice.candidate_member_count,
                        "price_count": choice.price_count,
                        "scored_count": choice.scored_count,
                        "price_coverage": choice.price_coverage,
                        "score_coverage": choice.score_coverage,
                        "tickers": list(choice.tickers),
                        "weights": dict(choice.weights),
                        "selection_mode": choice.selection_mode,
                        "correlation_lookback_days": choice.correlation_lookback_days,
                        "correlation_threshold": choice.correlation_threshold,
                        "correlation_observations": choice.correlation_observations,
                        "correlation_price_start": choice.correlation_price_start,
                        "correlation_price_end": choice.correlation_price_end,
                        "correlation_strict_asof_passed": (
                            choice.correlation_strict_asof_passed
                        ),
                        "correlation_pool_size": choice.correlation_pool_size,
                        "max_names_per_cluster": choice.max_names_per_cluster,
                        "cluster_max_weight": choice.cluster_max_weight,
                        "top_weight_count": choice.top_weight_count,
                        "top_weight_cap": choice.top_weight_cap,
                        "min_effective_n": choice.min_effective_n,
                        "cluster_labels": choice.cluster_labels,
                        "cluster_weights": choice.cluster_weights,
                        "max_pair_correlation": choice.max_pair_correlation,
                        "rejected_correlated_tickers": list(
                            choice.rejected_correlated_tickers
                        ),
                        "fundamental_score_weight": choice.fundamental_score_weight,
                        "quality_policy_id": choice.quality_policy_id,
                        "quality_score_coverage": choice.quality_score_coverage,
                        "quality_score_date": choice.quality_score_date,
                        "quality_future_data_guard_passed": (
                            choice.quality_future_data_guard_passed
                        ),
                        "quality_selection_mode": choice.quality_selection_mode,
                        "quality_challenge_pool_size": (
                            choice.quality_challenge_pool_size
                        ),
                        "max_quality_replacements": (
                            choice.max_quality_replacements
                        ),
                        "quality_challenge_pool_tickers": list(
                            choice.quality_challenge_pool_tickers
                        ),
                        "quality_replacement_pairs": list(
                            choice.quality_replacement_pairs
                        ),
                        "valuation_score_weight": choice.valuation_score_weight,
                        "valuation_policy_id": choice.valuation_policy_id,
                        "valuation_score_coverage": (
                            choice.valuation_score_coverage
                        ),
                        "valuation_observed_coverage": (
                            choice.valuation_observed_coverage
                        ),
                        "valuation_score_date": choice.valuation_score_date,
                        "valuation_future_data_guard_passed": (
                            choice.valuation_future_data_guard_passed
                        ),
                        "valuation_missing_neutral_count": (
                            choice.valuation_missing_neutral_count
                        ),
                        "max_names_per_sic4": choice.max_names_per_sic4,
                        "max_names_per_sic2": choice.max_names_per_sic2,
                        "sic4_max_weight": choice.sic4_max_weight,
                        "sic2_max_weight": choice.sic2_max_weight,
                        "sic4_by_ticker": choice.sic4_by_ticker,
                        "sic2_by_ticker": choice.sic2_by_ticker,
                        "sic4_weights": choice.sic4_weights,
                        "sic2_weights": choice.sic2_weights,
                        "rejected_sic_tickers": list(
                            choice.rejected_sic_tickers
                        ),
                        "rejected_sic_reasons": choice.rejected_sic_reasons,
                        "candidate_tickers": list(choice.candidate_tickers),
                        "churn": _selection_churn(prev_selection, current),
                        "turnover": traded,
                        "cost": cost,
                    })
                    prev_selection = current

        date_label = grid[i].strftime("%Y-%m-%d")
        alive_held = active_symbols(i)
        monthly_due = monthly > 0 and i > 0 and i % 21 == 0
        if monthly_due:
            value_now = (
                _symbols_value_at(symbols, panels, i, "close") if symbols else 0.0
            ) + float(cash)
            nav_before_flow = value_now / units if units > 0 else nav[i - 1]
            units += float(monthly) / nav_before_flow
            flows.append((i, float(monthly)))
            if not alive_held:
                cash += float(monthly)
        if not symbols:
            equity[i] = float(cash)
            nav[i] = equity[i] / units if units > 0 else 1.0
            continue
        cap_sum = sum(max(0.0, symbols[ticker].cap_total) for ticker in alive_held)
        for ticker in list(symbols):
            if not (listing_i.get(ticker, 0) <= i <= last_i.get(ticker, n - 1)):
                continue
            state = symbols[ticker]
            close = float(panels[ticker]["close"][i])
            open_price = float(panels[ticker]["open"][i])
            low = float(panels[ticker]["low"][i])
            eng.process_pending(state, close, i)
            if i > entry_i.get(ticker, i):
                eng.fire_tiers(state, open_price, low, date_label, cfg)
            if monthly_due and cap_sum > 0:
                eng.apply_injection(
                    state,
                    float(monthly) * state.cap_total / cap_sum,
                    close,
                    i,
                    cfg,
                )
            eng.update_high(state, close, cfg)
        total_value = _symbols_value_at(symbols, panels, i, "close") + float(cash)
        equity[i] = total_value
        nav[i] = total_value / units if units > 0 else (nav[i - 1] if i else 1.0)

    if not selections:
        reason = rebalance_failures[0]["reason"] if rebalance_failures else "unknown"
        raise NdxCompetitionError(
            f"no valid point-in-time NDX selections in window; first failure: {reason}"
        )
    stats = {
        "rebalance_months": int(rebalance_months),
        "trade_cost_bps": float(trade_cost_bps),
        "turnover": float(turnover),
        "cost_paid": float(cost_paid),
        "rebalance_count": len(selections),
        "failed_rebalances": int(failed_rebalances),
        "rebalance_failures": rebalance_failures,
        "selection_churn_p50": _q([item.get("churn") for item in selections], 0.50),
        "min_price_coverage": min(item["price_coverage"] for item in selections),
        "min_score_coverage": min(item["score_coverage"] for item in selections),
        "max_pair_correlation_p90": _q(
            [item.get("max_pair_correlation") for item in selections], 0.90
        ),
        "max_cluster_weight_p90": _q(
            [
                max((item.get("cluster_weights") or {}).values())
                if item.get("cluster_weights") else None
                for item in selections
            ],
            0.90,
        ),
        "max_top_weight_p90": _q(
            [
                sum(
                    sorted(
                        (item.get("weights") or {}).values(),
                        reverse=True,
                    )[:int(item["top_weight_count"])]
                )
                if item.get("top_weight_count") is not None else None
                for item in selections
            ],
            0.90,
        ),
        "observed_min_effective_n": _q(
            [
                1.0 / sum(
                    float(weight) ** 2
                    for weight in (item.get("weights") or {}).values()
                )
                if item.get("weights") else None
                for item in selections
            ],
            0.0,
        ),
        "correlation_rejected_p50": _q(
            [
                len(item.get("rejected_correlated_tickers") or [])
                for item in selections
                if item.get("correlation_observations") is not None
            ],
            0.50,
        ),
        "min_quality_score_coverage": _q(
            [item.get("quality_score_coverage") for item in selections], 0.0
        ),
        "quality_replacements_p50": _q(
            [
                len(item.get("quality_replacement_pairs") or [])
                for item in selections
                if item.get("quality_selection_mode") == "bounded_challenge"
            ],
            0.50,
        ),
        "quality_replacements_p90": _q(
            [
                len(item.get("quality_replacement_pairs") or [])
                for item in selections
                if item.get("quality_selection_mode") == "bounded_challenge"
            ],
            0.90,
        ),
        "max_sic4_weight_p90": _q(
            [
                max((item.get("sic4_weights") or {}).values())
                if item.get("sic4_weights") else None
                for item in selections
            ],
            0.90,
        ),
        "max_sic2_weight_p90": _q(
            [
                max((item.get("sic2_weights") or {}).values())
                if item.get("sic2_weights") else None
                for item in selections
            ],
            0.90,
        ),
        "sic_rejected_p50": _q(
            [
                len(item.get("rejected_sic_tickers") or [])
                for item in selections
                if item.get("quality_policy_id") is not None
            ],
            0.50,
        ),
        "selections": selections,
    }
    return nav, equity, flows, stats


def _incumbent_path(
    cfg,
    grid: pd.DatetimeIndex,
    panels: Mapping[str, dict],
    listing_i: Mapping[str, int],
    last_i: Mapping[str, int],
    *,
    total_cap: float,
    monthly: float,
    safe_annual: float,
    rebal_days: int,
    rebal_band: float,
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, float]], dict]:
    requested = [symbol for symbol in cfg.symbols if symbol.ticker in panels]
    if len(requested) != len(cfg.symbols):
        missing = sorted({symbol.ticker for symbol in cfg.symbols} - set(panels))
        raise NdxCompetitionError(f"incumbent price panels missing: {missing}")
    cap_sum = sum(float(symbol.cap_total) for symbol in requested)
    caps = {
        symbol.ticker: float(total_cap) * float(symbol.cap_total) / cap_sum
        for symbol in requested
    }
    _, risk_nav, risk_equity, _, flows = _run_strategy_fund(
        grid,
        {ticker: panels[ticker] for ticker in caps},
        {ticker: listing_i[ticker] for ticker in caps},
        {ticker: last_i[ticker] for ticker in caps},
        caps,
        float(monthly),
        cfg,
    )
    safe_weight = float(cfg.safe_leg.target_weight) if cfg.safe_leg else 0.0
    if safe_weight > 0:
        nav, equity, _, turnover, n_rebal = _run_defensive_fund(
            grid,
            risk_nav,
            flows,
            float(safe_annual),
            safe_weight,
            int(rebal_days),
            float(rebal_band),
        )
    else:
        nav, equity, turnover, n_rebal = risk_nav, risk_equity, 0.0, 0
    return nav, equity, flows, {
        "safe_weight": safe_weight,
        "turnover": float(turnover),
        "n_rebal": int(n_rebal),
    }


def _unitized_nav_from_equity(
    equity: np.ndarray,
    flows: list[tuple[int, float]],
) -> np.ndarray:
    values = np.asarray(equity, dtype=float)
    if values.ndim != 1 or not len(values):
        raise NdxCompetitionError("subaccount equity path is empty")
    flow_by_index: dict[int, float] = {}
    for index, amount in flows:
        parsed_index = int(index)
        if not 0 <= parsed_index < len(values):
            raise NdxCompetitionError("subaccount flow index is outside its path")
        flow_by_index[parsed_index] = (
            flow_by_index.get(parsed_index, 0.0) + float(amount)
        )
    if 0 not in flow_by_index or flow_by_index[0] <= 0:
        raise NdxCompetitionError("subaccount path has no positive initial flow")

    units = 0.0
    nav = np.zeros(len(values), dtype=float)
    for index, equity_value in enumerate(values):
        flow = float(flow_by_index.get(index, 0.0))
        if flow:
            if units == 0.0:
                nav_before_flow = 1.0
            else:
                equity_before_flow = float(equity_value) - flow
                nav_before_flow = equity_before_flow / units
            if not np.isfinite(nav_before_flow) or nav_before_flow <= 0:
                raise NdxCompetitionError("subaccount NAV before flow is invalid")
            units += flow / nav_before_flow
        if units <= 0 or not np.isfinite(equity_value) or equity_value <= 0:
            raise NdxCompetitionError("subaccount unitization inputs are invalid")
        nav[index] = float(equity_value) / units
    return nav


def _blend_incumbent_anchor(
    challenger_nav: np.ndarray,
    challenger_equity: np.ndarray,
    challenger_flows: list[tuple[int, float]],
    incumbent_nav: np.ndarray,
    incumbent_equity: np.ndarray,
    incumbent_flows: list[tuple[int, float]],
    *,
    challenger_weight: float,
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, float]]]:
    weight = float(challenger_weight)
    if not 0.0 < weight <= 1.0:
        raise NdxCompetitionError("challenger sleeve weight must be in (0, 1]")
    if len(challenger_equity) != len(incumbent_equity):
        raise NdxCompetitionError("challenger and incumbent paths are not aligned")
    if len(challenger_nav) != len(challenger_equity) or len(incumbent_nav) != len(
        incumbent_equity
    ):
        raise NdxCompetitionError("subaccount NAV and equity lengths differ")
    def aggregate(flows: list[tuple[int, float]]) -> dict[int, float]:
        result: dict[int, float] = {}
        for index, amount in flows:
            parsed = int(index)
            result[parsed] = result.get(parsed, 0.0) + float(amount)
        return result

    challenger_schedule = aggregate(challenger_flows)
    incumbent_schedule = aggregate(incumbent_flows)
    if (
        set(challenger_schedule) != set(incumbent_schedule)
        or any(
            not np.isclose(
                challenger_schedule[index], incumbent_schedule[index], atol=1e-8
            )
            for index in challenger_schedule
        )
    ):
        raise NdxCompetitionError("challenger and incumbent cash flows differ")
    flows = sorted(challenger_schedule.items())
    if np.isclose(weight, 1.0, atol=0.0):
        return (
            np.asarray(challenger_nav, dtype=float),
            np.asarray(challenger_equity, dtype=float),
            flows,
        )
    equity = (
        weight * np.asarray(challenger_equity, dtype=float)
        + (1.0 - weight) * np.asarray(incumbent_equity, dtype=float)
    )
    nav = _unitized_nav_from_equity(equity, flows)
    return nav, equity, flows


def _rollup_samples(samples: list[dict]) -> dict:
    return {
        "windows": len(samples),
        "distribution": {
            "strategy_xirr": _qs([item["strategy"].get("xirr") for item in samples]),
            "strategy_maxdd": _qs([item["strategy"].get("maxdd") for item in samples]),
        },
        "rolling_samples": [
            {
                "start": item["start"],
                "xirr": item["strategy"].get("xirr"),
                "maxdd": item["strategy"].get("maxdd"),
            }
            for item in samples
        ],
    }


def _candidate_rollup(
    key: tuple,
    samples: list[dict],
    *,
    target: str,
    incumbent: dict,
    policy,
) -> dict:
    if not samples:
        raise NdxCompetitionError(f"candidate {key!r} has no rolling samples")
    first = samples[0]
    lookback_years = float(first["lookback_years"])
    top_n = int(first["top_n"])
    weight_mode = str(first["weight_mode"])
    rebalance_months = int(first["rebalance_months"])
    safe_weight = float(first["safe_weight"])
    challenger_sleeve_weight = float(
        first.get("challenger_sleeve_weight", 1.0)
    )
    max_weight = float(first["max_weight"])
    excess = [item.get("excess_xirr") for item in samples]
    relief = [item.get("dd_relief") for item in samples]
    valid_excess = [value for value in excess if value is not None and np.isfinite(value)]
    valid_relief = [value for value in relief if value is not None and np.isfinite(value)]
    qqq_excess = [item.get("qqq_excess_xirr") for item in samples]
    qqq_relief = [item.get("qqq_dd_relief") for item in samples]
    valid_qqq_excess = [
        value for value in qqq_excess if value is not None and np.isfinite(value)
    ]
    valid_qqq_relief = [
        value for value in qqq_relief if value is not None and np.isfinite(value)
    ]
    incumbent_excess = [
        (
            item["strategy"].get("xirr") - item["incumbent"].get("xirr")
            if item.get("strategy", {}).get("xirr") is not None
            and item.get("incumbent", {}).get("xirr") is not None
            else None
        )
        for item in samples
    ]
    incumbent_relief = [
        (
            item["incumbent"].get("maxdd") - item["strategy"].get("maxdd")
            if item.get("strategy", {}).get("maxdd") is not None
            and item.get("incumbent", {}).get("maxdd") is not None
            else None
        )
        for item in samples
    ]
    valid_incumbent_excess = [
        value for value in incumbent_excess
        if value is not None and np.isfinite(value)
    ]
    valid_incumbent_relief = [
        value for value in incumbent_relief
        if value is not None and np.isfinite(value)
    ]
    base = _rollup_samples(samples)
    row = {
        "profile_id": first.get("profile_id"),
        "basket": first.get("basket") or f"top{top_n}_{weight_mode}",
        "lookback_years": float(lookback_years),
        "top_n": int(top_n),
        "weight_mode": weight_mode,
        "rebalance_months": int(rebalance_months),
        "safe_weight": float(safe_weight),
        "challenger_sleeve_weight": challenger_sleeve_weight,
        "max_weight": float(max_weight),
        "selection_mode": first.get("selection_mode", DEFAULT_SELECTION_MODE),
        "correlation_lookback_days": first.get("correlation_lookback_days"),
        "correlation_threshold": first.get("correlation_threshold"),
        "correlation_pool_size": first.get("correlation_pool_size"),
        "max_names_per_cluster": first.get("max_names_per_cluster"),
        "cluster_max_weight": first.get("cluster_max_weight"),
        "top_weight_count": first.get("top_weight_count"),
        "top_weight_cap": first.get("top_weight_cap"),
        "min_effective_n": first.get("min_effective_n"),
        "fundamental_score_weight": float(
            first.get("fundamental_score_weight") or 0.0
        ),
        "quality_policy_id": first.get("quality_policy_id"),
        "valuation_score_weight": float(
            first.get("valuation_score_weight") or 0.0
        ),
        "valuation_policy_id": first.get("valuation_policy_id"),
        "quality_selection_mode": first.get(
            "quality_selection_mode", DEFAULT_QUALITY_SELECTION_MODE
        ),
        "quality_challenge_pool_size": first.get(
            "quality_challenge_pool_size"
        ),
        "max_quality_replacements": int(
            first.get("max_quality_replacements") or 0
        ),
        "max_names_per_sic4": first.get("max_names_per_sic4"),
        "max_names_per_sic2": first.get("max_names_per_sic2"),
        "sic4_max_weight": first.get("sic4_max_weight"),
        "sic2_max_weight": first.get("sic2_max_weight"),
        "candidate_tickers": first.get("candidate_tickers") or "",
        "defense_mode": first.get("defense_mode", "static"),
        "defense_signal": first.get("defense_signal"),
        "target_vol": first.get("target_vol"),
        "defense_band": first.get("defense_band"),
        "defense_vol_window": first.get("defense_vol_window"),
        "defense_exec_band": first.get("defense_exec_band"),
        "defense_drawdown_lookback_days": first.get(
            "defense_drawdown_lookback_days"
        ),
        "defense_drawdown_trigger": first.get("defense_drawdown_trigger"),
        "defense_drawdown_full": first.get("defense_drawdown_full"),
        "defense_max_safe_weight": first.get("defense_max_safe_weight"),
        "defense_release_step": first.get("defense_release_step"),
        "min_weight": samples[0].get("min_weight") if samples else None,
        "trade_cost_bps": samples[0].get("trade_cost_bps") if samples else None,
        "windows": len(samples),
        "win_rate": float(np.mean([value > 0 for value in valid_excess])) if valid_excess else None,
        "dd_win_rate": float(np.mean([value > 0 for value in valid_relief])) if valid_relief else None,
        "excess_p50": _q(valid_excess, 0.50),
        "excess_p10": _q(valid_excess, 0.10),
        "dd_relief_p50": _q(valid_relief, 0.50),
        "dd_relief_p10": _q(valid_relief, 0.10),
        "qqq_win_rate": (
            float(np.mean([value > 0 for value in valid_qqq_excess]))
            if valid_qqq_excess else None
        ),
        "qqq_excess_p50": _q(valid_qqq_excess, 0.50),
        "qqq_excess_p10": _q(valid_qqq_excess, 0.10),
        "qqq_dd_relief_p50": _q(valid_qqq_relief, 0.50),
        "qqq_dd_relief_p10": _q(valid_qqq_relief, 0.10),
        "incumbent_win_rate": (
            float(np.mean([value > 0 for value in valid_incumbent_excess]))
            if valid_incumbent_excess else None
        ),
        "incumbent_dd_win_rate": (
            float(np.mean([value > 0 for value in valid_incumbent_relief]))
            if valid_incumbent_relief else None
        ),
        "incumbent_excess_p50": _q(valid_incumbent_excess, 0.50),
        "incumbent_excess_p10": _q(valid_incumbent_excess, 0.10),
        "incumbent_dd_relief_p50": _q(valid_incumbent_relief, 0.50),
        "incumbent_dd_relief_p10": _q(valid_incumbent_relief, 0.10),
        "turnover_x_p50": _q([item.get("turnover_x") for item in samples], 0.50),
        "cost_x_p50": _q([item.get("cost_x") for item in samples], 0.50),
        "selection_churn_p50": _q(
            [item.get("selection_churn_p50") for item in samples], 0.50
        ),
        "avg_safe_weight_p10": _q(
            [item.get("avg_safe_weight") for item in samples], 0.10
        ),
        "avg_safe_weight_p50": _q(
            [item.get("avg_safe_weight") for item in samples], 0.50
        ),
        "avg_safe_weight_p90": _q(
            [item.get("avg_safe_weight") for item in samples], 0.90
        ),
        "max_pair_correlation_p90": _q(
            [item.get("max_pair_correlation_p90") for item in samples], 0.90
        ),
        "max_cluster_weight_p90": _q(
            [item.get("max_cluster_weight_p90") for item in samples], 0.90
        ),
        "max_top_weight_p90": _q(
            [item.get("max_top_weight_p90") for item in samples], 0.90
        ),
        "observed_min_effective_n": _q(
            [item.get("observed_min_effective_n") for item in samples], 0.0
        ),
        "correlation_rejected_p50": _q(
            [item.get("correlation_rejected_p50") for item in samples], 0.50
        ),
        "min_quality_score_coverage": _q(
            [item.get("min_quality_score_coverage") for item in samples], 0.0
        ),
        "quality_replacements_p50": _q(
            [item.get("quality_replacements_p50") for item in samples], 0.50
        ),
        "quality_replacements_p90": _q(
            [item.get("quality_replacements_p90") for item in samples], 0.90
        ),
        "max_sic4_weight_p90": _q(
            [item.get("max_sic4_weight_p90") for item in samples], 0.90
        ),
        "max_sic2_weight_p90": _q(
            [item.get("max_sic2_weight_p90") for item in samples], 0.90
        ),
        "sic_rejected_p50": _q(
            [item.get("sic_rejected_p50") for item in samples], 0.50
        ),
        "defense_signal_prehistory_seeded": (
            all(item.get("defense_signal_prehistory_seeded") is True for item in samples)
            if first.get("defense_mode") in {"vol_target", "drawdown_guard"} else None
        ),
        "defense_signal_strict_asof_passed": (
            all(item.get("defense_signal_strict_asof_passed") is True for item in samples)
            if first.get("defense_mode") in {"vol_target", "drawdown_guard"} else None
        ),
        "min_price_coverage": min(item.get("min_price_coverage", 0.0) for item in samples),
        "min_score_coverage": min(item.get("min_score_coverage", 0.0) for item in samples),
        "tickers_observed": sorted({
            ticker for item in samples for ticker in item.get("tickers_observed", [])
        }),
        "range": [samples[0]["start"], samples[-1]["start"]] if samples else None,
        **base,
    }
    row["distribution"].update({
        "benchmark_xirr": _qs([item["benchmark"].get("xirr") for item in samples]),
        "benchmark_maxdd": _qs([item["benchmark"].get("maxdd") for item in samples]),
        "qqq_xirr": _qs([item["qqq"].get("xirr") for item in samples]),
        "qqq_maxdd": _qs([item["qqq"].get("maxdd") for item in samples]),
        "excess_xirr": _qs(excess),
        "dd_relief": _qs(relief),
        "qqq_excess_xirr": _qs(qqq_excess),
        "qqq_dd_relief": _qs(qqq_relief),
        "incumbent_excess_xirr": _qs(incumbent_excess),
        "incumbent_dd_relief": _qs(incumbent_relief),
    })
    row["target_envelope"] = evaluate_target_risk_envelope(
        row, target=target, policy=policy
    )
    row["incumbent_guard"] = evaluate_incumbent_risk_guard(
        row, incumbent, policy=policy
    )
    row["admission_passed"] = bool(
        row["target_envelope"].get("passed")
        and row["incumbent_guard"].get("passed")
    )
    return row


def _sort_value(value, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return parsed if np.isfinite(parsed) else float(fallback)


def _row_sort_key(row: dict) -> tuple:
    target = row.get("target_envelope") or {}
    incumbent = row.get("incumbent_guard") or {}
    return (
        bool(row.get("admission_passed")),
        bool(incumbent.get("passed")),
        bool(target.get("passed")),
        _sort_value(row.get("win_rate"), -1.0),
        _sort_value(row.get("excess_p10"), -9.0),
        _sort_value(row.get("excess_p50"), -9.0),
        _sort_value(row.get("dd_relief_p10"), -9.0),
        -_sort_value(row.get("turnover_x_p50"), 99.0),
        -int(row.get("top_n") or 99),
    )


def _incumbent_row_sort_key(row: dict) -> tuple:
    incumbent = row.get("incumbent_guard") or {}
    return (
        bool(incumbent.get("passed")),
        _sort_value(row.get("incumbent_win_rate"), -1.0),
        _sort_value(row.get("incumbent_excess_p10"), -9.0),
        _sort_value(row.get("incumbent_excess_p50"), -9.0),
        _sort_value(row.get("incumbent_dd_relief_p10"), -9.0),
        _sort_value(row.get("incumbent_dd_relief_p50"), -9.0),
        -_sort_value(row.get("turnover_x_p50"), 99.0),
        -int(row.get("top_n") or 99),
    )


def _qqq_sort_key(row: dict) -> tuple:
    return (
        _sort_value(row.get("qqq_win_rate"), -1.0),
        _sort_value(row.get("qqq_excess_p10"), -9.0),
        _sort_value(row.get("qqq_excess_p50"), -9.0),
        _sort_value(row.get("qqq_dd_relief_p10"), -9.0),
        _sort_value(row.get("qqq_dd_relief_p50"), -9.0),
    )


def _current_choice(
    ndx_current: pd.DataFrame,
    series: Mapping[str, pd.DataFrame],
    *,
    row: dict,
    asof: pd.Timestamp,
    source_snapshot: pd.DataFrame | None = None,
    source_evidence: dict | None = None,
    quality_scores: pd.DataFrame | None = None,
    valuation_scores: pd.DataFrame | None = None,
) -> dict:
    if row.get("defense_mode") in {"vol_target", "drawdown_guard"}:
        return {
            "available": False,
            "reason": (
                "current dynamic safe weight depends on a declared live NAV history; "
                "it is not inferred from rolling research windows"
            ),
        }
    if row.get("weight_mode") == "source_weight":
        if source_snapshot is None or source_evidence is None:
            return {
                "available": False,
                "reason": "current official NDX/QQQ weights are unavailable; source weight is not guessed",
            }
        source_by_ticker = {
            str(item.ticker).upper(): float(item.weight)
            for item in source_snapshot.itertuples(index=False)
        }
        current_weights = ndx_current["ticker"].astype(str).str.upper().map(source_by_ticker)
    else:
        current_weights = np.nan
    snapshot = pd.DataFrame({
        "ticker": ndx_current["ticker"].astype(str).str.upper(),
        "weight": current_weights,
    })
    evidence = {
        "selection_date": pd.Timestamp(asof).strftime("%Y-%m-%d"),
        "source": "Nasdaq official current companies page",
        "security_count": len(snapshot),
        "current_snapshot_only": True,
    }
    if source_evidence is not None and row.get("weight_mode") == "source_weight":
        evidence.update({
            "weight_source": "QQQ SEC N-PORT public filing",
            "weight_report_date": source_evidence.get("report_date"),
            "weight_available_date": source_evidence.get("available_date"),
            "weight_accession_number": source_evidence.get("accession_number"),
            "weight_is_current": False,
        })
    choice = _choose_from_snapshot(
        snapshot,
        evidence,
        asof=asof,
        series=series,
        top_n=int(row["top_n"]),
        weight_mode=str(row["weight_mode"]),
        lookback_days=max(252, int(float(row["lookback_years"]) * 252)),
        min_history_days=126,
        max_weight=float(row["max_weight"]),
        min_weight=float(row.get("min_weight") or 0.02),
        selection_mode=str(row.get("selection_mode") or DEFAULT_SELECTION_MODE),
        correlation_lookback_days=int(
            row.get("correlation_lookback_days") or DEFAULT_CORRELATION_LOOKBACK_DAYS
        ),
        correlation_threshold=float(
            row.get("correlation_threshold") or DEFAULT_CORRELATION_THRESHOLD
        ),
        correlation_pool_size=int(row.get("correlation_pool_size") or 0),
        max_names_per_cluster=int(row.get("max_names_per_cluster") or 1),
        cluster_max_weight=row.get("cluster_max_weight"),
        top_weight_count=row.get("top_weight_count"),
        top_weight_cap=row.get("top_weight_cap"),
        min_effective_n=row.get("min_effective_n"),
        quality_scores=quality_scores,
        fundamental_score_weight=float(
            row.get("fundamental_score_weight") or 0.0
        ),
        quality_policy_id=row.get("quality_policy_id"),
        valuation_scores=valuation_scores,
        valuation_score_weight=float(row.get("valuation_score_weight") or 0.0),
        valuation_policy_id=row.get("valuation_policy_id"),
        quality_selection_mode=str(
            row.get("quality_selection_mode")
            or DEFAULT_QUALITY_SELECTION_MODE
        ),
        quality_challenge_pool_size=row.get("quality_challenge_pool_size"),
        max_quality_replacements=int(
            row.get("max_quality_replacements") or 0
        ),
        max_names_per_sic4=row.get("max_names_per_sic4"),
        max_names_per_sic2=row.get("max_names_per_sic2"),
        sic4_max_weight=row.get("sic4_max_weight"),
        sic2_max_weight=row.get("sic2_max_weight"),
        candidate_tickers=row.get("candidate_tickers"),
    )
    safe_weight = float(row.get("safe_weight") or 0.0)
    challenger_sleeve_weight = float(
        row.get("challenger_sleeve_weight", 1.0)
    )
    return {
        "available": True,
        "selection_date": choice.selection_date,
        "top_n": choice.top_n,
        "weight_mode": choice.weight_mode,
        "selection_mode": choice.selection_mode,
        "max_weight": float(row["max_weight"]),
        "top_weight_count": choice.top_weight_count,
        "top_weight_cap": choice.top_weight_cap,
        "min_effective_n": choice.min_effective_n,
        "safe_weight": safe_weight,
        "challenger_sleeve_weight": challenger_sleeve_weight,
        "incumbent_anchor_weight": 1.0 - challenger_sleeve_weight,
        "safe_ticker": "SGOV" if safe_weight > 0 else None,
        "membership_evidence": choice.membership_evidence,
        "price_coverage": choice.price_coverage,
        "score_coverage": choice.score_coverage,
        "fundamental_score_weight": choice.fundamental_score_weight,
        "quality_policy_id": choice.quality_policy_id,
        "quality_score_coverage": choice.quality_score_coverage,
        "quality_score_date": choice.quality_score_date,
        "quality_future_data_guard_passed": (
            choice.quality_future_data_guard_passed
        ),
        "quality_selection_mode": choice.quality_selection_mode,
        "quality_challenge_pool_size": choice.quality_challenge_pool_size,
        "max_quality_replacements": choice.max_quality_replacements,
        "quality_challenge_pool_tickers": list(
            choice.quality_challenge_pool_tickers
        ),
        "quality_replacement_pairs": list(choice.quality_replacement_pairs),
        "valuation_score_weight": choice.valuation_score_weight,
        "valuation_policy_id": choice.valuation_policy_id,
        "valuation_score_coverage": choice.valuation_score_coverage,
        "valuation_observed_coverage": choice.valuation_observed_coverage,
        "valuation_score_date": choice.valuation_score_date,
        "valuation_future_data_guard_passed": (
            choice.valuation_future_data_guard_passed
        ),
        "valuation_missing_neutral_count": (
            choice.valuation_missing_neutral_count
        ),
        "sic4_weights": choice.sic4_weights,
        "sic2_weights": choice.sic2_weights,
        "security_count": choice.expected_count,
        "issuer_count": choice.expected_issuer_count,
        "candidate_member_count": choice.candidate_member_count,
        "candidate_tickers": list(choice.candidate_tickers),
        "holdings": [
            {
                "ticker": ticker,
                "risk_sleeve_weight": float(choice.weights[ticker]),
                "portfolio_weight": (
                    float(choice.weights[ticker])
                    * (1.0 - safe_weight)
                    * challenger_sleeve_weight
                ),
            }
            for ticker in choice.tickers
        ],
    }


def run_ndx_competition_research(
    cfg,
    *,
    total_cap: float = 37000.0,
    monthly: float = 3000.0,
    target_benchmark: str = "012922",
    min_years: float = 1.5,
    lookback_years: float = 3.0,
    min_history_years: float = 0.5,
    top_ns: str | Iterable[int] = DEFAULT_TOP_NS,
    weight_modes: str | Iterable[str] = DEFAULT_WEIGHT_MODES,
    safe_weights: str | Iterable[float] = "0,0.26",
    rebalance_months: str | Iterable[int] = DEFAULT_REBALANCE_MONTHS,
    max_weights: str | Iterable[float] = "0.25,0.35",
    trade_cost_bps: float = 10.0,
    safe_annual: float = 0.04,
    rebal_days: int = 21,
    rebal_band: float = 0.15,
    step_months: int = 3,
    max_windows: int = 0,
    local_only: bool = True,
    include_samples: bool = False,
    construction_profiles: Iterable[Mapping[str, Any]] | None = None,
    comparison_priority: str = "target_then_incumbent",
) -> dict:
    """Compare individual NDX constituents with point-in-time membership."""
    priority = str(comparison_priority or "target_then_incumbent").strip().lower()
    if priority not in SUPPORTED_COMPARISON_PRIORITIES:
        raise NdxCompetitionError(
            f"unsupported comparison priority: {comparison_priority!r}"
        )
    c = _research_cfg(cfg, local_only)
    history, history_meta = get_ndx_point_in_time_history(c)
    history_report = history_coverage_report(history)
    current_ndx, current_meta = get_nasdaq_100_snapshot(c)
    requested = sorted(
        set(history["ticker"].astype(str).str.upper())
        | set(current_ndx["ticker"].astype(str).str.upper())
        | {symbol.ticker for symbol in c.symbols}
    )
    series, price_meta, price_errors = _load_series(c, requested)
    price_version = _price_universe_version(series)
    if price_errors:
        missing_union = sorted(set(history["ticker"].astype(str).str.upper()) & set(price_errors))
        if missing_union:
            raise NdxCompetitionError(
                f"historical NDX price load incomplete: {missing_union}"
            )
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, c.data.start_date, c.data.end_date
    )
    target = str(target_benchmark or "012922").upper().strip()
    target_close, target_meta = _fetch_benchmark_close(target, c, grid)
    qqq_close, qqq_meta = _fetch_benchmark_close("QQQ", c, grid)
    target_start = _first_valid_price_i(target_close)
    target_version = data_version_payload(
        target_meta,
        used_start=grid[target_start].strftime("%Y-%m-%d") if target_start is not None else None,
        used_end=grid[-1].strftime("%Y-%m-%d"),
    )
    qqq_version = data_version_payload(
        qqq_meta,
        used_start=grid[0].strftime("%Y-%m-%d"),
        used_end=grid[-1].strftime("%Y-%m-%d"),
    )

    min_len = max(2, int(float(min_years) * 252))
    lookback_days = max(252, int(float(lookback_years) * 252))
    min_history_days = max(63, int(float(min_history_years) * 252))
    starts = []
    for start_index in _monthly_start_indexes(grid, min_len, step_months):
        if not np.isfinite(float(target_close[start_index])) or float(target_close[start_index]) <= 0:
            continue
        try:
            constituents_asof(history, grid[start_index])
        except NdxHistoryError:
            continue
        starts.append(start_index)
    if max_windows and max_windows > 0:
        starts = starts[:int(max_windows)]
    if not starts:
        raise NdxCompetitionError("no valid rolling starts after point-in-time membership guard")

    top_values = _parse_ints(top_ns, DEFAULT_TOP_NS)
    mode_values = _parse_modes(weight_modes)
    safe_values = parse_safe_weights(safe_weights)
    rebalance_values = _parse_ints(rebalance_months, DEFAULT_REBALANCE_MONTHS)
    max_weight_values = _parse_weight_caps(max_weights)
    profiles = _normalize_construction_profiles(
        construction_profiles,
        lookback_years=float(lookback_years),
        top_values=top_values,
        mode_values=mode_values,
        safe_values=safe_values,
        rebalance_values=rebalance_values,
        max_weight_values=max_weight_values,
    )
    quality_scores = None
    quality_score_meta = None
    if any(_profile_requires_quality_evidence(profile) for profile in profiles):
        try:
            quality_scores, quality_score_meta = load_quality_score_evidence(c)
        except Exception as exc:
            raise NdxCompetitionError(
                f"point-in-time quality evidence is unavailable: {exc}"
            ) from exc
    valuation_scores = None
    valuation_score_meta = None
    valuation_policy_id = _valuation_policy_for_profiles(profiles)
    if valuation_policy_id is not None:
        try:
            valuation_scores, valuation_score_meta = load_valuation_score_evidence(
                c, valuation_policy_id
            )
        except Exception as exc:
            raise NdxCompetitionError(
                f"point-in-time valuation evidence is unavailable: {exc}"
            ) from exc
    for profile in profiles:
        profile["_sample_key"] = profile.get("profile_id") or (
            float(lookback_years),
            int(profile["top_n"]),
            str(profile["weight_mode"]),
            int(profile["rebalance_months"]),
            float(profile["safe_weight"]),
            float(profile["max_weight"]),
        )
        profile["_risk_key"] = (
            int(profile["top_n"]),
            str(profile["weight_mode"]),
            int(profile["rebalance_months"]),
            float(profile["max_weight"]),
            float(profile["min_weight"]),
            str(profile["selection_mode"]),
            profile.get("correlation_lookback_days"),
            profile.get("correlation_threshold"),
            profile.get("correlation_pool_size"),
            profile.get("max_names_per_cluster"),
            profile.get("cluster_max_weight"),
            profile.get("top_weight_count"),
            profile.get("top_weight_cap"),
            profile.get("min_effective_n"),
            float(profile.get("fundamental_score_weight") or 0.0),
            profile.get("quality_policy_id"),
            float(profile.get("valuation_score_weight") or 0.0),
            profile.get("valuation_policy_id"),
            profile.get("quality_selection_mode"),
            profile.get("quality_challenge_pool_size"),
            int(profile.get("max_quality_replacements") or 0),
            profile.get("max_names_per_sic4"),
            profile.get("max_names_per_sic2"),
            profile.get("sic4_max_weight"),
            profile.get("sic2_max_weight"),
            tuple(profile.get("candidate_tickers") or ()),
        )
    samples_by_key = {profile["_sample_key"]: [] for profile in profiles}
    profiles_by_risk: dict[tuple, list[dict]] = {}
    for profile in profiles:
        profiles_by_risk.setdefault(profile["_risk_key"], []).append(profile)
    incumbent_samples = []
    benchmark_cache = {}
    incumbent_cache = {}
    choice_cache = {}
    correlation_cache = {}
    defense_signal_cache = {}
    skipped = []

    for start_index in starts:
        grid_window = grid[start_index:]
        alive = [ticker for ticker in panels if last_i[ticker] >= start_index]
        panels_window = {
            ticker: {
                field: np.asarray(values[start_index:], dtype=float)
                for field, values in panels[ticker].items()
            }
            for ticker in alive
        }
        listing_window = {ticker: max(0, listing_i[ticker] - start_index) for ticker in alive}
        last_window = {ticker: last_i[ticker] - start_index for ticker in alive}
        start_label = grid_window[0].strftime("%Y-%m-%d")

        if start_label not in incumbent_cache:
            inc_nav, inc_equity, inc_flows, inc_stats = _incumbent_path(
                c,
                grid_window,
                panels_window,
                listing_window,
                last_window,
                total_cap=float(total_cap),
                monthly=float(monthly),
                safe_annual=float(safe_annual),
                rebal_days=int(rebal_days),
                rebal_band=float(rebal_band),
            )
            incumbent_cache[start_label] = (
                _metric_block(
                    grid_window,
                    inc_nav,
                    inc_equity,
                    inc_flows,
                    sum(value for _, value in inc_flows),
                    inc_stats["turnover"],
                    inc_stats["n_rebal"],
                ),
                inc_flows,
                inc_nav,
                inc_equity,
                inc_stats,
            )
        (
            incumbent_metric,
            incumbent_flows,
            incumbent_nav,
            incumbent_equity,
            incumbent_stats,
        ) = incumbent_cache[start_label]
        incumbent_samples.append({
            "start": start_label,
            "strategy": incumbent_metric,
        })

        for risk_key, risk_profiles in profiles_by_risk.items():
            risk_profile = risk_profiles[0]
            try:
                risk_nav, risk_equity, flows, stats = _active_ndx_risk_leg(
                    c,
                    grid_window,
                    panels_window,
                    listing_window,
                    last_window,
                    series,
                    history,
                    top_n=int(risk_profile["top_n"]),
                    weight_mode=str(risk_profile["weight_mode"]),
                    total_cap=float(total_cap),
                    monthly=float(monthly),
                    lookback_days=lookback_days,
                    min_history_days=min_history_days,
                    rebalance_months=int(risk_profile["rebalance_months"]),
                    trade_cost_bps=float(trade_cost_bps),
                    max_weight=float(risk_profile["max_weight"]),
                    min_weight=float(risk_profile["min_weight"]),
                    selection_mode=str(risk_profile["selection_mode"]),
                    correlation_lookback_days=risk_profile.get(
                        "correlation_lookback_days"
                    ),
                    correlation_threshold=risk_profile.get("correlation_threshold"),
                    correlation_pool_size=risk_profile.get("correlation_pool_size"),
                    max_names_per_cluster=risk_profile.get("max_names_per_cluster"),
                    cluster_max_weight=risk_profile.get("cluster_max_weight"),
                    top_weight_count=risk_profile.get("top_weight_count"),
                    top_weight_cap=risk_profile.get("top_weight_cap"),
                    min_effective_n=risk_profile.get("min_effective_n"),
                    quality_scores=quality_scores,
                    fundamental_score_weight=float(
                        risk_profile.get("fundamental_score_weight") or 0.0
                    ),
                    quality_policy_id=risk_profile.get("quality_policy_id"),
                    valuation_scores=valuation_scores,
                    valuation_score_weight=float(
                        risk_profile.get("valuation_score_weight") or 0.0
                    ),
                    valuation_policy_id=risk_profile.get("valuation_policy_id"),
                    quality_selection_mode=str(
                        risk_profile.get("quality_selection_mode")
                        or DEFAULT_QUALITY_SELECTION_MODE
                    ),
                    quality_challenge_pool_size=risk_profile.get(
                        "quality_challenge_pool_size"
                    ),
                    max_quality_replacements=int(
                        risk_profile.get("max_quality_replacements") or 0
                    ),
                    max_names_per_sic4=risk_profile.get("max_names_per_sic4"),
                    max_names_per_sic2=risk_profile.get("max_names_per_sic2"),
                    sic4_max_weight=risk_profile.get("sic4_max_weight"),
                    sic2_max_weight=risk_profile.get("sic2_max_weight"),
                    candidate_tickers=tuple(
                        risk_profile.get("candidate_tickers") or ()
                    ),
                    choice_cache=choice_cache,
                    correlation_cache=correlation_cache,
                )
            except Exception as exc:
                skipped.append({
                    "start": start_label,
                    "profile_ids": ";".join(
                        str(item.get("profile_id") or "legacy")
                        for item in risk_profiles
                    ),
                    "top_n": int(risk_profile["top_n"]),
                    "weight_mode": risk_profile["weight_mode"],
                    "rebalance_months": int(risk_profile["rebalance_months"]),
                    "max_weight": float(risk_profile["max_weight"]),
                    "selection_mode": risk_profile["selection_mode"],
                    "top_weight_count": risk_profile.get("top_weight_count"),
                    "top_weight_cap": risk_profile.get("top_weight_cap"),
                    "min_effective_n": risk_profile.get("min_effective_n"),
                    "fundamental_score_weight": float(
                        risk_profile.get("fundamental_score_weight") or 0.0
                    ),
                    "quality_policy_id": risk_profile.get("quality_policy_id"),
                    "valuation_score_weight": float(
                        risk_profile.get("valuation_score_weight") or 0.0
                    ),
                    "valuation_policy_id": risk_profile.get("valuation_policy_id"),
                    "quality_selection_mode": risk_profile.get(
                        "quality_selection_mode"
                    ),
                    "quality_challenge_pool_size": risk_profile.get(
                        "quality_challenge_pool_size"
                    ),
                    "max_quality_replacements": int(
                        risk_profile.get("max_quality_replacements") or 0
                    ),
                    "max_names_per_sic4": risk_profile.get("max_names_per_sic4"),
                    "max_names_per_sic2": risk_profile.get("max_names_per_sic2"),
                    "sic4_max_weight": risk_profile.get("sic4_max_weight"),
                    "sic2_max_weight": risk_profile.get("sic2_max_weight"),
                    "reason": str(exc),
                })
                continue
            contributed = sum(value for _, value in flows)
            if contributed <= 0:
                continue
            benchmark_key = (start_label, tuple(flows))
            if benchmark_key not in benchmark_cache:
                target_nav, target_equity = _run_single_asset_fund(
                    grid_window, target_close[start_index:], flows
                )
                qqq_nav, qqq_equity = _run_single_asset_fund(
                    grid_window, qqq_close[start_index:], flows
                )
                benchmark_cache[benchmark_key] = (
                    _metric_block(
                        grid_window, target_nav, target_equity, flows, contributed
                    ),
                    _metric_block(
                        grid_window, qqq_nav, qqq_equity, flows, contributed
                    ),
                )
            benchmark, qqq_benchmark = benchmark_cache[benchmark_key]
            observed = sorted({
                ticker
                for selection in stats.get("selections", [])
                for ticker in selection.get("tickers", [])
            })

            for profile in risk_profiles:
                safe_weight = float(profile["safe_weight"])
                defense = _apply_defense_profile(
                    grid_window,
                    risk_nav,
                    risk_equity,
                    flows,
                    stats.get("selections") or [],
                    series,
                    profile,
                    safe_annual=float(safe_annual),
                    rebal_days=int(rebal_days),
                    rebal_band=float(rebal_band),
                    trade_cost_bps=float(trade_cost_bps),
                    defense_signal_cache=defense_signal_cache,
                )
                nav = defense["nav"]
                equity = defense["equity"]
                safe_turnover = defense["safe_turnover"]
                safe_rebalances = defense["safe_rebalances"]
                avg_safe_weight = defense["avg_safe_weight"]
                min_safe_weight = defense["min_safe_weight"]
                max_safe_weight = defense["max_safe_weight"]
                defense_signal_meta = defense["defense_signal_meta"]
                challenger_turnover = float(stats.get("turnover") or 0.0) + float(
                    safe_turnover
                )
                challenger_cost = float(stats.get("cost_paid") or 0.0) + float(
                    defense["safe_cost_paid"]
                )
                challenger_sleeve_weight = float(
                    profile.get("challenger_sleeve_weight", 1.0)
                )
                nav, equity, strategy_flows = _blend_incumbent_anchor(
                    nav,
                    equity,
                    flows,
                    incumbent_nav,
                    incumbent_equity,
                    incumbent_flows,
                    challenger_weight=challenger_sleeve_weight,
                )
                incumbent_anchor_weight = 1.0 - challenger_sleeve_weight
                total_turnover = (
                    challenger_sleeve_weight * challenger_turnover
                    + incumbent_anchor_weight
                    * float(incumbent_stats.get("turnover") or 0.0)
                )
                total_cost = challenger_sleeve_weight * challenger_cost
                combined_safe_turnover = (
                    challenger_sleeve_weight * float(safe_turnover)
                    + incumbent_anchor_weight
                    * float(incumbent_stats.get("turnover") or 0.0)
                )
                if incumbent_anchor_weight > 0:
                    avg_safe_weight = None
                    min_safe_weight = None
                    max_safe_weight = None
                strategy = _metric_block(
                    grid_window,
                    nav,
                    equity,
                    strategy_flows,
                    contributed,
                    total_turnover,
                    int(safe_rebalances)
                    + (
                        int(incumbent_stats.get("n_rebal") or 0)
                        if incumbent_anchor_weight > 0 else 0
                    ),
                )
                strategy["challenger_sleeve_weight"] = challenger_sleeve_weight
                strategy["incumbent_anchor_weight"] = incumbent_anchor_weight
                strategy["avg_safe_weight"] = avg_safe_weight
                strategy["min_safe_weight"] = min_safe_weight
                strategy["max_safe_weight"] = max_safe_weight
                excess = (
                    strategy["xirr"] - benchmark["xirr"]
                    if strategy.get("xirr") is not None
                    and benchmark.get("xirr") is not None
                    else None
                )
                relief = (
                    benchmark["maxdd"] - strategy["maxdd"]
                    if strategy.get("maxdd") is not None
                    and benchmark.get("maxdd") is not None
                    else None
                )
                qqq_excess = (
                    strategy["xirr"] - qqq_benchmark["xirr"]
                    if strategy.get("xirr") is not None
                    and qqq_benchmark.get("xirr") is not None
                    else None
                )
                qqq_relief = (
                    qqq_benchmark["maxdd"] - strategy["maxdd"]
                    if strategy.get("maxdd") is not None
                    and qqq_benchmark.get("maxdd") is not None
                    else None
                )
                sample = {
                    "start": start_label,
                    "end": grid_window[-1].strftime("%Y-%m-%d"),
                    "profile_id": profile.get("profile_id"),
                    "basket": profile.get("profile_id") or (
                        f"top{profile['top_n']}_{profile['weight_mode']}"
                    ),
                    "lookback_years": float(lookback_years),
                    "top_n": int(profile["top_n"]),
                    "weight_mode": profile["weight_mode"],
                    "rebalance_months": int(profile["rebalance_months"]),
                    "safe_weight": safe_weight,
                    "challenger_sleeve_weight": float(
                        profile.get("challenger_sleeve_weight", 1.0)
                    ),
                    "max_weight": float(profile["max_weight"]),
                    "min_weight": float(profile["min_weight"]),
                    "selection_mode": profile["selection_mode"],
                    "correlation_lookback_days": profile.get(
                        "correlation_lookback_days"
                    ),
                    "correlation_threshold": profile.get("correlation_threshold"),
                    "correlation_pool_size": profile.get("correlation_pool_size"),
                    "max_names_per_cluster": profile.get("max_names_per_cluster"),
                    "cluster_max_weight": profile.get("cluster_max_weight"),
                    "top_weight_count": profile.get("top_weight_count"),
                    "top_weight_cap": profile.get("top_weight_cap"),
                    "min_effective_n": profile.get("min_effective_n"),
                    "fundamental_score_weight": float(
                        profile.get("fundamental_score_weight") or 0.0
                    ),
                    "quality_policy_id": profile.get("quality_policy_id"),
                    "valuation_score_weight": float(
                        profile.get("valuation_score_weight") or 0.0
                    ),
                    "valuation_policy_id": profile.get("valuation_policy_id"),
                    "quality_selection_mode": profile.get(
                        "quality_selection_mode",
                        DEFAULT_QUALITY_SELECTION_MODE,
                    ),
                    "quality_challenge_pool_size": profile.get(
                        "quality_challenge_pool_size"
                    ),
                    "max_quality_replacements": int(
                        profile.get("max_quality_replacements") or 0
                    ),
                    "max_names_per_sic4": profile.get("max_names_per_sic4"),
                    "max_names_per_sic2": profile.get("max_names_per_sic2"),
                    "sic4_max_weight": profile.get("sic4_max_weight"),
                    "sic2_max_weight": profile.get("sic2_max_weight"),
                    "candidate_tickers": ";".join(
                        profile.get("candidate_tickers") or ()
                    ),
                    "defense_mode": profile["defense_mode"],
                    "defense_signal": profile.get("defense_signal"),
                    "target_vol": profile.get("target_vol"),
                    "defense_band": profile.get("defense_band"),
                    "defense_vol_window": profile.get("defense_vol_window"),
                    "defense_exec_band": profile.get("defense_exec_band"),
                    "defense_drawdown_lookback_days": profile.get(
                        "defense_drawdown_lookback_days"
                    ),
                    "defense_drawdown_trigger": profile.get(
                        "defense_drawdown_trigger"
                    ),
                    "defense_drawdown_full": profile.get("defense_drawdown_full"),
                    "defense_max_safe_weight": profile.get(
                        "defense_max_safe_weight"
                    ),
                    "defense_release_step": profile.get("defense_release_step"),
                    "avg_safe_weight": avg_safe_weight,
                    "min_safe_weight": min_safe_weight,
                    "max_safe_weight": max_safe_weight,
                    "defense_signal_prehistory_seeded": (
                        defense_signal_meta.get("prehistory_seeded")
                        if defense_signal_meta else None
                    ),
                    "defense_signal_strict_asof_passed": (
                        defense_signal_meta.get("strict_asof_passed")
                        if defense_signal_meta else None
                    ),
                    "defense_signal_first_date": (
                        defense_signal_meta.get("first_signal_date")
                        if defense_signal_meta else None
                    ),
                    "defense_signal_last_date": (
                        defense_signal_meta.get("last_signal_date")
                        if defense_signal_meta else None
                    ),
                    "trade_cost_bps": float(trade_cost_bps),
                    "tickers_observed": observed,
                    "turnover_x": total_turnover / contributed,
                    "safe_turnover_x": float(combined_safe_turnover) / contributed,
                    "cost_x": total_cost / contributed,
                    "selection_churn_p50": stats.get("selection_churn_p50"),
                    "min_price_coverage": stats.get("min_price_coverage"),
                    "min_score_coverage": stats.get("min_score_coverage"),
                    "max_pair_correlation_p90": stats.get(
                        "max_pair_correlation_p90"
                    ),
                    "max_cluster_weight_p90": stats.get(
                        "max_cluster_weight_p90"
                    ),
                    "max_top_weight_p90": stats.get("max_top_weight_p90"),
                    "observed_min_effective_n": stats.get(
                        "observed_min_effective_n"
                    ),
                    "correlation_rejected_p50": stats.get(
                        "correlation_rejected_p50"
                    ),
                    "min_quality_score_coverage": stats.get(
                        "min_quality_score_coverage"
                    ),
                    "quality_replacements_p50": stats.get(
                        "quality_replacements_p50"
                    ),
                    "quality_replacements_p90": stats.get(
                        "quality_replacements_p90"
                    ),
                    "max_sic4_weight_p90": stats.get("max_sic4_weight_p90"),
                    "max_sic2_weight_p90": stats.get("max_sic2_weight_p90"),
                    "sic_rejected_p50": stats.get("sic_rejected_p50"),
                    "strategy": strategy,
                    "benchmark": benchmark,
                    "qqq": qqq_benchmark,
                    "incumbent": incumbent_metric,
                    "excess_xirr": excess,
                    "dd_relief": relief,
                    "qqq_excess_xirr": qqq_excess,
                    "qqq_dd_relief": qqq_relief,
                }
                if include_samples:
                    sample["selections"] = stats.get("selections", [])
                samples_by_key[profile["_sample_key"]].append(sample)

    incumbent_rollup = {
        "available": True,
        "source": "config_yaml",
        "basket": "current_config",
        "safe_weight": float(c.safe_leg.target_weight) if c.safe_leg else 0.0,
        **_rollup_samples(incumbent_samples),
    }
    policy = getattr(c, "research_admission", None)
    rows = [
        _candidate_rollup(
            key,
            samples,
            target=target,
            incumbent=incumbent_rollup,
            policy=policy,
        )
        for key, samples in samples_by_key.items()
        if samples
    ]
    rows.sort(
        key=(
            _incumbent_row_sort_key
            if priority == "incumbent_first" else _row_sort_key
        ),
        reverse=True,
    )
    best_qqq = max(rows, key=_qqq_sort_key) if rows else None
    current_asof = grid[-1] + pd.Timedelta(days=1)
    current_snapshot_date = pd.Timestamp(current_meta.as_of_date)
    current_snapshot_usable = (
        current_snapshot_date <= current_asof
        and int((current_asof.normalize() - current_snapshot_date.normalize()).days)
        <= MAX_PRICE_AGE_CALENDAR_DAYS
    )
    current_selection = {
        "available": False,
        "reason": (
            "official current Nasdaq snapshot is outside the research end-date; "
            "historical current selection is not reconstructed from future membership"
        ),
    }
    current_selection_basis = None
    current_selection_best_qqq = copy.deepcopy(current_selection)
    current_selection_best_qqq_basis = None
    if current_snapshot_usable:
        current_source_snapshot, current_source_evidence = constituents_asof(
            history, current_asof
        )
        for row in rows:
            try:
                selection = _current_choice(
                    current_ndx,
                    series,
                    row=row,
                    asof=current_asof,
                    source_snapshot=current_source_snapshot,
                    source_evidence=current_source_evidence,
                    quality_scores=quality_scores,
                    valuation_scores=valuation_scores,
                )
            except Exception:
                continue
            if selection.get("available"):
                current_selection = selection
                current_selection_basis = {
                    "profile_id": row.get("profile_id"),
                    "basket": row["basket"],
                    "lookback_years": row["lookback_years"],
                    "rebalance_months": row["rebalance_months"],
                    "max_weight": row["max_weight"],
                    "safe_weight": row["safe_weight"],
                    "selection_mode": row.get("selection_mode"),
                    "defense_mode": row.get("defense_mode"),
                    "admission_passed": row["admission_passed"],
                    "target_classification": row["target_envelope"]["classification"],
                    "incumbent_guard_passed": row["incumbent_guard"]["passed"],
                }
                break
        if best_qqq is not None:
            try:
                selection = _current_choice(
                    current_ndx,
                    series,
                    row=best_qqq,
                    asof=current_asof,
                    source_snapshot=current_source_snapshot,
                    source_evidence=current_source_evidence,
                    quality_scores=quality_scores,
                    valuation_scores=valuation_scores,
                )
            except Exception:
                selection = None
            if selection and selection.get("available"):
                current_selection_best_qqq = selection
                current_selection_best_qqq_basis = {
                    "profile_id": best_qqq.get("profile_id"),
                    "basket": best_qqq["basket"],
                    "lookback_years": best_qqq["lookback_years"],
                    "rebalance_months": best_qqq["rebalance_months"],
                    "max_weight": best_qqq["max_weight"],
                    "safe_weight": best_qqq["safe_weight"],
                    "selection_mode": best_qqq.get("selection_mode"),
                    "defense_mode": best_qqq.get("defense_mode"),
                    "qqq_win_rate": best_qqq.get("qqq_win_rate"),
                    "qqq_excess_p50": best_qqq.get("qqq_excess_p50"),
                    "qqq_excess_p10": best_qqq.get("qqq_excess_p10"),
                    "qqq_dd_relief_p50": best_qqq.get("qqq_dd_relief_p50"),
                    "admission_passed": best_qqq["admission_passed"],
                }

    output = {
        "summary": {
            "generated_at": utc_now_iso(),
            "research_only": True,
            "does_change_today_advice": False,
            "candidate_assets": "Nasdaq-100 individual securities",
            "qqq_role": "benchmark_only_not_candidate",
            "qqq_performance_role": (
                "optimization_target" if target == "QQQ" else "auxiliary_reference_only"
            ),
            "method": "ndx_point_in_time_active_competition",
            "comparison_priority": priority,
            "primary_competition_benchmark": (
                "current_config" if priority == "incumbent_first" else target
            ),
            "target_benchmark": target,
            "target_label": _benchmark_label(target),
            "lookback_years": float(lookback_years),
            "min_history_years": float(min_history_years),
            "history_requirement": "full_lookback_window",
            "max_price_age_calendar_days": MAX_PRICE_AGE_CALENDAR_DAYS,
            "min_years": float(min_years),
            "step_months": int(step_months),
            "start_count": len(starts),
            "top_ns": top_values,
            "weight_modes": mode_values,
            "safe_weights": safe_values,
            "rebalance_months": rebalance_values,
            "max_weights": max_weight_values,
            "trade_cost_bps": float(trade_cost_bps),
            "construction_profile_count": len(profiles),
            "explicit_construction_profiles": bool(construction_profiles is not None),
            "construction_profiles": [
                {key: value for key, value in profile.items() if not key.startswith("_")}
                for profile in profiles
            ] if construction_profiles is not None else None,
            "row_count": len(rows),
            "admission_pass_count": sum(bool(row.get("admission_passed")) for row in rows),
            "best": rows[0] if rows else None,
            "best_qqq": best_qqq,
            "current_selection_basis": current_selection_basis,
            "current_selection_best_qqq_basis": current_selection_best_qqq_basis,
            "note": (
                "每次选择先恢复当日已公开的约100只个股，再用此前价格竞争；"
                "QQQ只作基准。结果不写config/state，不改变今日建议。"
            ),
        },
        "current_selection": current_selection,
        "current_selection_best_qqq": current_selection_best_qqq,
        "incumbent": incumbent_rollup,
        "data_manifest": {
            "schema_version": 1,
            "ndx_history": history_meta.to_dict(),
            "ndx_current": current_meta.to_dict(),
            "target_nav": target_version,
            "qqq_benchmark": qqq_version,
            "price_universe": price_version,
            **(
                {"quality_scores": quality_score_meta}
                if quality_score_meta is not None else {}
            ),
            **(
                {"valuation_scores": valuation_score_meta}
                if valuation_score_meta is not None else {}
            ),
            "future_data_guard": "available_date <= selection_date",
        },
        "history_coverage": history_report,
        "price_coverage": coverage,
        "price_meta": price_meta,
        "price_errors": price_errors,
        "rows": rows,
        "skipped": skipped[:200],
    }
    if include_samples:
        output["samples"] = [
            sample for samples in samples_by_key.values() for sample in samples
        ]
    return output


def run_ndx_profile_trace(
    cfg,
    profile: Mapping[str, Any],
    *,
    window_start: str,
    target_benchmark: str = "012922",
    total_cap: float = 37000.0,
    monthly: float = 3000.0,
    lookback_years: float = 1.0,
    min_history_years: float = 0.5,
    trade_cost_bps: float = 10.0,
    safe_annual: float = 0.04,
    rebal_days: int = 21,
    rebal_band: float = 0.15,
    local_only: bool = True,
) -> dict:
    """Replay one declared profile and expose its daily point-in-time path."""
    c = _research_cfg(cfg, local_only)
    history, history_meta = get_ndx_point_in_time_history(c)
    current_ndx, _ = get_nasdaq_100_snapshot(c)
    requested = sorted(
        set(history["ticker"].astype(str).str.upper())
        | set(current_ndx["ticker"].astype(str).str.upper())
        | {symbol.ticker for symbol in c.symbols}
    )
    series, _, price_errors = _load_series(c, requested)
    if price_errors:
        missing = sorted(set(history["ticker"].astype(str).str.upper()) & set(price_errors))
        if missing:
            raise NdxCompetitionError(f"historical NDX price load incomplete: {missing}")
    grid, panels, listing_i, last_i, _ = _build_panels(
        series, c.data.start_date, c.data.end_date
    )
    start_date = pd.Timestamp(window_start)
    start_index = int(grid.searchsorted(start_date))
    if (
        start_index >= len(grid)
        or grid[start_index].strftime("%Y-%m-%d") != start_date.strftime("%Y-%m-%d")
    ):
        raise NdxCompetitionError(f"window start is not a trading date: {window_start}")
    normalized = _normalize_construction_profiles(
        [profile],
        lookback_years=float(lookback_years),
        top_values=[int(profile.get("top_n") or 0)],
        mode_values=[str(profile.get("weight_mode") or "")],
        safe_values=[float(profile.get("safe_weight") or 0.0)],
        rebalance_values=[int(profile.get("rebalance_months") or 0)],
        max_weight_values=[float(profile.get("max_weight") or 0.0)],
    )[0]
    quality_scores = None
    quality_score_meta = None
    if _profile_requires_quality_evidence(normalized):
        try:
            quality_scores, quality_score_meta = load_quality_score_evidence(c)
        except Exception as exc:
            raise NdxCompetitionError(
                f"point-in-time quality evidence is unavailable: {exc}"
            ) from exc
    valuation_scores = None
    valuation_score_meta = None
    valuation_policy_id = _valuation_policy_for_profiles([normalized])
    if valuation_policy_id is not None:
        try:
            valuation_scores, valuation_score_meta = load_valuation_score_evidence(
                c, valuation_policy_id
            )
        except Exception as exc:
            raise NdxCompetitionError(
                f"point-in-time valuation evidence is unavailable: {exc}"
            ) from exc

    grid_window = grid[start_index:]
    alive = [ticker for ticker in panels if last_i[ticker] >= start_index]
    panels_window = {
        ticker: {
            field: np.asarray(values[start_index:], dtype=float)
            for field, values in panels[ticker].items()
        }
        for ticker in alive
    }
    listing_window = {
        ticker: max(0, listing_i[ticker] - start_index) for ticker in alive
    }
    last_window = {ticker: last_i[ticker] - start_index for ticker in alive}
    lookback_days = max(252, int(float(lookback_years) * 252))
    min_history_days = max(63, int(float(min_history_years) * 252))
    risk_nav, risk_equity, flows, risk_stats = _active_ndx_risk_leg(
        c,
        grid_window,
        panels_window,
        listing_window,
        last_window,
        series,
        history,
        top_n=int(normalized["top_n"]),
        weight_mode=str(normalized["weight_mode"]),
        total_cap=float(total_cap),
        monthly=float(monthly),
        lookback_days=lookback_days,
        min_history_days=min_history_days,
        rebalance_months=int(normalized["rebalance_months"]),
        trade_cost_bps=float(trade_cost_bps),
        max_weight=float(normalized["max_weight"]),
        min_weight=float(normalized["min_weight"]),
        selection_mode=str(normalized["selection_mode"]),
        correlation_lookback_days=normalized.get("correlation_lookback_days"),
        correlation_threshold=normalized.get("correlation_threshold"),
        correlation_pool_size=normalized.get("correlation_pool_size"),
        max_names_per_cluster=normalized.get("max_names_per_cluster"),
        cluster_max_weight=normalized.get("cluster_max_weight"),
        top_weight_count=normalized.get("top_weight_count"),
        top_weight_cap=normalized.get("top_weight_cap"),
        min_effective_n=normalized.get("min_effective_n"),
        quality_scores=quality_scores,
        fundamental_score_weight=float(
            normalized.get("fundamental_score_weight") or 0.0
        ),
        quality_policy_id=normalized.get("quality_policy_id"),
        valuation_scores=valuation_scores,
        valuation_score_weight=float(
            normalized.get("valuation_score_weight") or 0.0
        ),
        valuation_policy_id=normalized.get("valuation_policy_id"),
        quality_selection_mode=str(
            normalized.get("quality_selection_mode")
            or DEFAULT_QUALITY_SELECTION_MODE
        ),
        quality_challenge_pool_size=normalized.get(
            "quality_challenge_pool_size"
        ),
        max_quality_replacements=int(
            normalized.get("max_quality_replacements") or 0
        ),
        max_names_per_sic4=normalized.get("max_names_per_sic4"),
        max_names_per_sic2=normalized.get("max_names_per_sic2"),
        sic4_max_weight=normalized.get("sic4_max_weight"),
        sic2_max_weight=normalized.get("sic2_max_weight"),
        candidate_tickers=tuple(normalized.get("candidate_tickers") or ()),
        choice_cache={},
        correlation_cache={},
    )
    defense = _apply_defense_profile(
        grid_window,
        risk_nav,
        risk_equity,
        flows,
        risk_stats.get("selections") or [],
        series,
        normalized,
        safe_annual=float(safe_annual),
        rebal_days=int(rebal_days),
        rebal_band=float(rebal_band),
        trade_cost_bps=float(trade_cost_bps),
        defense_signal_cache={},
    )
    incumbent_nav, incumbent_equity, incumbent_flows, incumbent_stats = _incumbent_path(
        c,
        grid_window,
        panels_window,
        listing_window,
        last_window,
        total_cap=float(total_cap),
        monthly=float(monthly),
        safe_annual=float(safe_annual),
        rebal_days=int(rebal_days),
        rebal_band=float(rebal_band),
    )
    challenger_sleeve_weight = float(
        normalized.get("challenger_sleeve_weight", 1.0)
    )
    strategy_nav, strategy_equity, strategy_flows = _blend_incumbent_anchor(
        defense["nav"],
        defense["equity"],
        flows,
        incumbent_nav,
        incumbent_equity,
        incumbent_flows,
        challenger_weight=challenger_sleeve_weight,
    )
    target = str(target_benchmark or "012922").upper().strip()
    target_close, target_meta = _fetch_benchmark_close(target, c, grid)
    target_nav, target_equity = _run_single_asset_fund(
        grid_window, target_close[start_index:], flows
    )

    selections = sorted(
        risk_stats.get("selections") or [], key=lambda item: str(item.get("date") or "")
    )
    active_tickers = []
    active_weights = []
    selection_dates = []
    pointer = 0
    active = selections[0]
    for date in grid_window:
        label = date.strftime("%Y-%m-%d")
        while pointer + 1 < len(selections) and selections[pointer + 1]["date"] <= label:
            pointer += 1
            active = selections[pointer]
        selection_dates.append(active["date"])
        active_tickers.append(";".join(active.get("tickers") or []))
        active_weights.append(";".join(
            f"{ticker}:{float(weight):.8f}"
            for ticker, weight in sorted((active.get("weights") or {}).items())
        ))

    def drawdown(nav: np.ndarray) -> np.ndarray:
        peaks = np.maximum.accumulate(nav)
        return np.where(peaks > 0, 1.0 - nav / peaks, 0.0)

    daily = pd.DataFrame({
        "date": grid_window,
        "risk_nav": risk_nav,
        "strategy_nav": strategy_nav,
        "strategy_equity": strategy_equity,
        "incumbent_nav": incumbent_nav,
        "incumbent_equity": incumbent_equity,
        "target_nav": target_nav,
        "target_equity": target_equity,
        "risk_drawdown": drawdown(risk_nav),
        "strategy_drawdown": drawdown(strategy_nav),
        "incumbent_drawdown": drawdown(incumbent_nav),
        "target_drawdown": drawdown(target_nav),
        "target_safe_weight": defense["safe_weight_series"],
        "raw_target_safe_weight": defense["raw_safe_weight_series"],
        "actual_safe_weight": defense["actual_safe_weight_series"],
        "challenger_sleeve_weight": challenger_sleeve_weight,
        "incumbent_anchor_weight": 1.0 - challenger_sleeve_weight,
        "selection_date": selection_dates,
        "tickers": active_tickers,
        "weights": active_weights,
    })
    contributed = sum(value for _, value in flows)
    strategy_metric = _metric_block(
        grid_window,
        strategy_nav,
        strategy_equity,
        strategy_flows,
        contributed,
        (
            challenger_sleeve_weight
            * (
                float(risk_stats.get("turnover") or 0.0)
                + float(defense["safe_turnover"])
            )
            + (1.0 - challenger_sleeve_weight)
            * float(incumbent_stats.get("turnover") or 0.0)
        ),
        int(defense["safe_rebalances"])
        + (
            int(incumbent_stats.get("n_rebal") or 0)
            if challenger_sleeve_weight < 1.0 else 0
        ),
    )
    incumbent_metric = _metric_block(
        grid_window,
        incumbent_nav,
        incumbent_equity,
        incumbent_flows,
        sum(value for _, value in incumbent_flows),
        incumbent_stats["turnover"],
        incumbent_stats["n_rebal"],
    )
    target_metric = _metric_block(
        grid_window, target_nav, target_equity, flows, contributed
    )

    def maxdd_event(column: str) -> dict:
        index = int(daily[column].to_numpy(dtype=float).argmax())
        return {
            "date": daily.iloc[index]["date"].strftime("%Y-%m-%d"),
            "drawdown": float(daily.iloc[index][column]),
            "target_safe_weight": float(daily.iloc[index]["target_safe_weight"]),
            "actual_safe_weight": float(daily.iloc[index]["actual_safe_weight"]),
            "tickers": daily.iloc[index]["tickers"],
            "weights": daily.iloc[index]["weights"],
        }

    return {
        "profile": normalized,
        "window_start": grid_window[0].strftime("%Y-%m-%d"),
        "window_end": grid_window[-1].strftime("%Y-%m-%d"),
        "target_benchmark": target,
        "trade_cost_bps": float(trade_cost_bps),
        "strategy": strategy_metric,
        "incumbent": incumbent_metric,
        "target": target_metric,
        "strategy_maxdd_event": maxdd_event("strategy_drawdown"),
        "incumbent_maxdd_event": maxdd_event("incumbent_drawdown"),
        "defense": {
            key: value for key, value in defense.items()
            if key not in {
                "nav",
                "equity",
                "safe_weight_series",
                "raw_safe_weight_series",
                "actual_safe_weight_series",
            }
        },
        "risk_stats": risk_stats,
        "history_version_id": history_meta.to_dict().get("version_id"),
        "price_version": _price_universe_version(series),
        "quality_score_version": quality_score_meta,
        "valuation_score_version": valuation_score_meta,
        "target_source": getattr(target_meta, "source", None),
        "daily": daily,
    }
