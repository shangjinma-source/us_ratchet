"""Research-only NDX quality scores from point-in-time SEC evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from data.ndx_fundamentals import NdxFundamentalError, fundamental_cache_dir
from data.versioning import file_sha256, manifest_path


QUALITY_POLICY_ID = "ndx_sec_quality_three_sleeve_v1"
GROWTH_FACTORS = ("revenue_growth",)
PROFITABILITY_FACTORS = (
    "operating_margin",
    "free_cash_flow_margin",
    "operating_cash_flow_to_assets",
)
BALANCE_FACTORS = ("equity_to_assets", "cash_to_assets")
CORE_FACTORS = GROWTH_FACTORS + PROFITABILITY_FACTORS + BALANCE_FACTORS
DIAGNOSTIC_FACTORS = (
    "net_margin",
    "research_and_development_intensity",
)


def load_quality_score_evidence(cfg) -> tuple[pd.DataFrame, dict]:
    directory = fundamental_cache_dir(cfg) / "quality_v1"
    bundle_manifest_path = directory / "manifest.json"
    if not bundle_manifest_path.exists():
        raise NdxFundamentalError(
            f"quality evidence manifest is missing: {bundle_manifest_path}"
        )
    bundle = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
    if bundle.get("research_ranking_ready") is not True:
        raise NdxFundamentalError("quality evidence ranking gate did not pass")
    if bundle.get("return_data_read") is not False:
        raise NdxFundamentalError("quality evidence unexpectedly read return data")
    evidence = (bundle.get("evidence_files") or {}).get("quality_scores") or {}
    path = directory / str(evidence.get("filename") or "")
    if (
        not path.exists()
        or not evidence.get("sha256")
        or file_sha256(path) != evidence["sha256"]
    ):
        raise NdxFundamentalError("quality score evidence hash mismatch")
    dataset_manifest_path = manifest_path(path)
    if not dataset_manifest_path.exists():
        raise NdxFundamentalError("quality score dataset manifest is missing")
    dataset_manifest = json.loads(
        dataset_manifest_path.read_text(encoding="utf-8")
    )
    if dataset_manifest.get("content_sha256") != evidence["sha256"]:
        raise NdxFundamentalError("quality score dataset version mismatch")
    frame = pd.read_csv(
        path,
        low_memory=False,
        dtype={"sic_group_2d": str},
    )
    required = {
        "selection_date",
        "ticker",
        "cik",
        "quality_score",
        "quality_eligible",
        "quality_policy_id",
        "sic",
        "sic_group_2d",
    }
    missing = sorted(required - set(frame.columns))
    if missing or frame.empty:
        raise NdxFundamentalError(
            f"quality score evidence is empty or incomplete: {missing}"
        )
    duplicates = frame.duplicated(["selection_date", "ticker"], keep=False)
    if duplicates.any():
        raise NdxFundamentalError("quality score evidence has duplicate ticker dates")
    return frame, {
        "version_id": dataset_manifest.get("version_id"),
        "content_sha256": dataset_manifest.get("content_sha256"),
        "source": dataset_manifest.get("source"),
        "source_locator": dataset_manifest.get("source_locator"),
        "data_start": dataset_manifest.get("data_start"),
        "data_end": dataset_manifest.get("data_end"),
        "row_count": dataset_manifest.get("row_count"),
        "quality_policy_id": QUALITY_POLICY_ID,
        "manifest_path": dataset_manifest_path.as_posix(),
        "cache_path": path.as_posix(),
        "future_data_guard": "quality selection_date equals rebalance date",
    }


def quality_snapshot(scores: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    date_label = pd.Timestamp(asof).strftime("%Y-%m-%d")
    snapshot = scores[scores["selection_date"].astype(str).eq(date_label)].copy()
    if snapshot.empty:
        raise NdxFundamentalError(
            f"quality score snapshot is unavailable for {date_label}"
        )
    if snapshot["quality_policy_id"].astype(str).nunique() != 1 or (
        snapshot["quality_policy_id"].astype(str).iloc[0] != QUALITY_POLICY_ID
    ):
        raise NdxFundamentalError("quality policy identity changed")
    return snapshot.set_index(snapshot["ticker"].astype(str).str.upper())


def sic_capped_weights(
    raw_weights: pd.Series,
    classifications: pd.DataFrame,
    *,
    max_weight: float,
    min_weight: float,
    max_weight_sic4: float | None,
    max_weight_sic2: float | None,
) -> pd.Series:
    raw = pd.to_numeric(raw_weights, errors="coerce").astype(float)
    if raw.empty or raw.isna().any() or (raw <= 0).any():
        raise NdxFundamentalError("SIC-capped weights require positive raw weights")
    tickers = list(raw.index.astype(str))
    classes = classifications.reindex(tickers)
    if classes[["sic", "sic_group_2d"]].isna().any().any():
        raise NdxFundamentalError("SIC-capped weights have missing classifications")
    n = len(tickers)
    floor = min(max(0.0, float(min_weight)), 1.0 / n)
    cap = max(float(max_weight), 1.0 / n)
    target = (raw / float(raw.sum())).to_numpy(dtype=float)
    groups = []
    for column, group_cap in (
        ("sic", max_weight_sic4),
        ("sic_group_2d", max_weight_sic2),
    ):
        if group_cap is None:
            continue
        parsed_cap = float(group_cap)
        if not 0.0 < parsed_cap <= 1.0:
            raise NdxFundamentalError(f"{column} weight cap is invalid")
        for _, names in classes.groupby(column).groups.items():
            indexes = np.asarray([tickers.index(name) for name in names], dtype=int)
            groups.append((column, indexes, parsed_cap))
    constraints = [{"type": "eq", "fun": lambda w: float(w.sum() - 1.0)}]
    constraints.extend({
        "type": "ineq",
        "fun": lambda w, idx=indexes, limit=group_cap: float(
            limit - w[idx].sum()
        ),
    } for _, indexes, group_cap in groups)
    result = minimize(
        lambda weights: float(np.sum((weights - target) ** 2)),
        np.repeat(1.0 / n, n),
        method="SLSQP",
        bounds=[(floor, cap)] * n,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12, "disp": False},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise NdxFundamentalError(
            f"SIC weight constraints are infeasible: {result.message}"
        )
    weights = pd.Series(result.x, index=tickers, dtype=float)
    weights /= float(weights.sum())
    tolerance = 1e-8
    if weights.max() > cap + tolerance or weights.min() < floor - tolerance:
        raise NdxFundamentalError("SIC optimizer violated ticker bounds")
    for column, indexes, group_cap in groups:
        if float(weights.iloc[indexes].sum()) > group_cap + tolerance:
            raise NdxFundamentalError(f"SIC optimizer violated {column} cap")
    return weights


@dataclass(frozen=True)
class QualityPolicy:
    winsor_lower: float = 0.05
    winsor_upper: float = 0.95
    minimum_core_factors: int = 5
    minimum_profitability_factors: int = 2
    required_balance_factors: int = 2
    sleeve_weight_growth: float = 1.0 / 3.0
    sleeve_weight_profitability: float = 1.0 / 3.0
    sleeve_weight_balance: float = 1.0 / 3.0
    preview_top_n: int = 6
    max_names_per_sic4: int = 2
    max_names_per_sic2: int = 3

    def validate(self) -> None:
        if not 0 <= self.winsor_lower < self.winsor_upper <= 1:
            raise NdxFundamentalError("quality winsor bounds are invalid")
        if not 1 <= self.minimum_core_factors <= len(CORE_FACTORS):
            raise NdxFundamentalError("quality core-factor minimum is invalid")
        if not 1 <= self.minimum_profitability_factors <= len(PROFITABILITY_FACTORS):
            raise NdxFundamentalError("profitability-factor minimum is invalid")
        if not 1 <= self.required_balance_factors <= len(BALANCE_FACTORS):
            raise NdxFundamentalError("balance-factor minimum is invalid")
        weights = (
            self.sleeve_weight_growth,
            self.sleeve_weight_profitability,
            self.sleeve_weight_balance,
        )
        if any(not np.isfinite(value) or value < 0 for value in weights):
            raise NdxFundamentalError("quality sleeve weights are invalid")
        if not np.isclose(sum(weights), 1.0, rtol=0, atol=1e-12):
            raise NdxFundamentalError("quality sleeve weights must sum to one")
        if self.preview_top_n <= 0:
            raise NdxFundamentalError("quality preview top N must be positive")
        if self.max_names_per_sic4 <= 0 or self.max_names_per_sic2 <= 0:
            raise NdxFundamentalError("quality SIC name caps must be positive")


def _required_columns() -> set[str]:
    columns = {"selection_date", "ticker", "cik"}
    for factor in CORE_FACTORS + DIAGNOSTIC_FACTORS:
        columns.update({factor, f"{factor}_status"})
    return columns


def _factor_percentiles(
    group: pd.DataFrame,
    factor: str,
    policy: QualityPolicy,
) -> tuple[pd.Series, list[dict]]:
    raw = pd.to_numeric(group[factor], errors="coerce")
    ready = group[f"{factor}_status"].eq("ready") & raw.notna() & np.isfinite(raw)
    ranked = pd.Series(np.nan, index=group.index, dtype=float)
    lower = raw[ready].quantile(policy.winsor_lower) if ready.any() else np.nan
    upper = raw[ready].quantile(policy.winsor_upper) if ready.any() else np.nan
    clipped = raw.clip(lower=lower, upper=upper) if ready.any() else raw
    if ready.any():
        ranked.loc[ready] = clipped.loc[ready].rank(
            method="average", pct=True, ascending=True
        )
    audit = []
    for index, row in group.iterrows():
        value = raw.loc[index]
        audit.append({
            "selection_date": row["selection_date"],
            "ticker": row["ticker"],
            "cik": int(row["cik"]),
            "factor": factor,
            "source_status": row[f"{factor}_status"],
            "raw_value": float(value) if pd.notna(value) else None,
            "winsor_lower": float(lower) if np.isfinite(lower) else None,
            "winsor_upper": float(upper) if np.isfinite(upper) else None,
            "winsorized_value": (
                float(clipped.loc[index])
                if ready.loc[index] and pd.notna(clipped.loc[index]) else None
            ),
            "percentile": (
                float(ranked.loc[index]) if pd.notna(ranked.loc[index]) else None
            ),
            "was_winsorized": bool(
                ready.loc[index]
                and (
                    value < lower
                    or value > upper
                )
            ),
            "included_in_quality_score": factor in CORE_FACTORS,
        })
    return ranked, audit


def build_quality_scores(
    factor_inputs: pd.DataFrame,
    sic_evidence: pd.DataFrame,
    *,
    policy: QualityPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return quality scores, long-form factor audit, and date coverage."""
    selected_policy = policy or QualityPolicy()
    selected_policy.validate()
    missing_factors = sorted(_required_columns() - set(factor_inputs.columns))
    required_sic = {
        "selection_date",
        "ticker",
        "cik",
        "sic",
        "sic_description",
        "sic_group_2d",
        "sic_division",
        "sic_available",
        "sic_future_data_guard_passed",
    }
    missing_sic = sorted(required_sic - set(sic_evidence.columns))
    if missing_factors or missing_sic:
        raise NdxFundamentalError(
            f"quality evidence columns missing: factors={missing_factors} sic={missing_sic}"
        )
    factors = factor_inputs.drop_duplicates(["selection_date", "ticker"])
    sic = sic_evidence[list(required_sic)].drop_duplicates(
        ["selection_date", "ticker"]
    )
    merged = factors.merge(
        sic,
        on=["selection_date", "ticker", "cik"],
        how="left",
        validate="one_to_one",
    )
    if merged["sic"].isna().any() or not bool(merged["sic_available"].all()):
        raise NdxFundamentalError("quality score has incomplete SIC evidence")
    if not bool(merged["sic_future_data_guard_passed"].all()):
        raise NdxFundamentalError("quality score SIC future-data guard failed")
    score_frames = []
    audit_rows = []
    for selection_date, group in merged.groupby("selection_date", sort=True):
        group = group.copy()
        for factor in CORE_FACTORS + DIAGNOSTIC_FACTORS:
            percentile, audit = _factor_percentiles(group, factor, selected_policy)
            group[f"{factor}_percentile"] = percentile
            audit_rows.extend(audit)
        group["core_factor_count"] = group[
            [f"{factor}_percentile" for factor in CORE_FACTORS]
        ].notna().sum(axis=1)
        group["profitability_factor_count"] = group[
            [f"{factor}_percentile" for factor in PROFITABILITY_FACTORS]
        ].notna().sum(axis=1)
        group["balance_factor_count"] = group[
            [f"{factor}_percentile" for factor in BALANCE_FACTORS]
        ].notna().sum(axis=1)
        group["growth_sleeve"] = group[
            [f"{factor}_percentile" for factor in GROWTH_FACTORS]
        ].mean(axis=1, skipna=False)
        group["profitability_sleeve"] = group[
            [f"{factor}_percentile" for factor in PROFITABILITY_FACTORS]
        ].mean(axis=1, skipna=True)
        group["balance_sleeve"] = group[
            [f"{factor}_percentile" for factor in BALANCE_FACTORS]
        ].mean(axis=1, skipna=True)
        group["quality_eligible"] = (
            group["core_factor_count"].ge(selected_policy.minimum_core_factors)
            & group["growth_sleeve"].notna()
            & group["profitability_factor_count"].ge(
                selected_policy.minimum_profitability_factors
            )
            & group["balance_factor_count"].ge(
                selected_policy.required_balance_factors
            )
        )
        group["quality_score"] = np.where(
            group["quality_eligible"],
            100.0 * (
                selected_policy.sleeve_weight_growth * group["growth_sleeve"]
                + selected_policy.sleeve_weight_profitability
                * group["profitability_sleeve"]
                + selected_policy.sleeve_weight_balance * group["balance_sleeve"]
            ),
            np.nan,
        )
        group["quality_confidence"] = np.where(
            ~group["quality_eligible"],
            "rejected",
            np.where(
                group["core_factor_count"].eq(len(CORE_FACTORS)),
                "high",
                "medium",
            ),
        )
        group["quality_policy_id"] = QUALITY_POLICY_ID
        score_frames.append(group)
    scores = pd.concat(score_frames, ignore_index=True)
    factor_audit = pd.DataFrame(audit_rows)
    coverage = scores.groupby("selection_date").agg(
        universe_count=("ticker", "size"),
        eligible_count=("quality_eligible", "sum"),
        score_coverage=("quality_eligible", "mean"),
        high_confidence_count=(
            "quality_confidence", lambda series: int(series.eq("high").sum())
        ),
        medium_confidence_count=(
            "quality_confidence", lambda series: int(series.eq("medium").sum())
        ),
        sic4_count=("sic", "nunique"),
        sic2_count=("sic_group_2d", "nunique"),
    ).reset_index()
    return scores, factor_audit, coverage


def select_with_sic_name_caps(
    ranked: pd.DataFrame,
    *,
    top_n: int,
    max_names_per_sic4: int,
    max_names_per_sic2: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"ticker", "cik", "sic", "sic_group_2d", "quality_score"}
    missing = sorted(required - set(ranked.columns))
    if missing:
        raise NdxFundamentalError(f"SIC selection columns missing: {missing}")
    if top_n <= 0 or max_names_per_sic4 <= 0 or max_names_per_sic2 <= 0:
        raise NdxFundamentalError("SIC selection limits must be positive")
    ordered = ranked[ranked["quality_score"].notna()].sort_values(
        ["quality_score", "revenue_growth_percentile", "ticker"],
        ascending=[False, False, True],
        kind="stable",
    ).drop_duplicates("cik", keep="first")
    selected_indexes = []
    rejection_rows = []
    sic4_counts: dict[int, int] = {}
    sic2_counts: dict[str, int] = {}
    for index, row in ordered.iterrows():
        sic4 = int(row["sic"])
        sic2 = str(row["sic_group_2d"])
        reason = None
        if sic4_counts.get(sic4, 0) >= int(max_names_per_sic4):
            reason = "sic4_name_cap"
        elif sic2_counts.get(sic2, 0) >= int(max_names_per_sic2):
            reason = "sic2_name_cap"
        if reason is not None:
            rejection_rows.append({
                "ticker": row["ticker"],
                "quality_score": row["quality_score"],
                "sic": sic4,
                "sic_group_2d": sic2,
                "reason": reason,
            })
            continue
        selected_indexes.append(index)
        sic4_counts[sic4] = sic4_counts.get(sic4, 0) + 1
        sic2_counts[sic2] = sic2_counts.get(sic2, 0) + 1
        if len(selected_indexes) >= int(top_n):
            break
    if len(selected_indexes) != int(top_n):
        raise NdxFundamentalError(
            f"SIC limits selected {len(selected_indexes)} names for top{top_n}"
        )
    selected = ordered.loc[selected_indexes].copy()
    selected["selection_rank"] = range(1, len(selected) + 1)
    return selected, pd.DataFrame(rejection_rows)


def quality_selection_previews(
    scores: pd.DataFrame,
    *,
    policy: QualityPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected_policy = policy or QualityPolicy()
    selected_policy.validate()
    preview_rows = []
    rejection_rows = []
    concentration_rows = []
    for selection_date, group in scores.groupby("selection_date", sort=True):
        eligible = group[group["quality_eligible"]].sort_values(
            ["quality_score", "revenue_growth_percentile", "ticker"],
            ascending=[False, False, True],
            kind="stable",
        ).drop_duplicates("cik", keep="first")
        unconstrained = eligible.head(selected_policy.preview_top_n)
        constrained, rejected = select_with_sic_name_caps(
            group,
            top_n=selected_policy.preview_top_n,
            max_names_per_sic4=selected_policy.max_names_per_sic4,
            max_names_per_sic2=selected_policy.max_names_per_sic2,
        )
        unconstrained_sic4_max = int(unconstrained.groupby("sic").size().max())
        unconstrained_sic2_max = int(
            unconstrained.groupby("sic_group_2d").size().max()
        )
        concentration_rows.append({
            "selection_date": selection_date,
            "top_n": selected_policy.preview_top_n,
            "unconstrained_max_names_sic4": unconstrained_sic4_max,
            "unconstrained_max_names_sic2": unconstrained_sic2_max,
            "unconstrained_sic4_cap_passed": (
                unconstrained_sic4_max <= selected_policy.max_names_per_sic4
            ),
            "unconstrained_sic2_cap_passed": (
                unconstrained_sic2_max <= selected_policy.max_names_per_sic2
            ),
            "constrained_unique_sic4": int(constrained["sic"].nunique()),
            "constrained_unique_sic2": int(
                constrained["sic_group_2d"].nunique()
            ),
            "rejected_before_fill": len(rejected),
        })
        for mode, frame in (
            ("unconstrained", unconstrained),
            ("sic_constrained", constrained),
        ):
            for position, row in enumerate(frame.itertuples(index=False), start=1):
                preview_rows.append({
                    "selection_date": selection_date,
                    "mode": mode,
                    "rank": position,
                    "ticker": row.ticker,
                    "cik": int(row.cik),
                    "quality_score": float(row.quality_score),
                    "quality_confidence": row.quality_confidence,
                    "sic": int(row.sic),
                    "sic_description": row.sic_description,
                    "sic_group_2d": str(row.sic_group_2d),
                    "sic_division": row.sic_division,
                })
        if not rejected.empty:
            rejected = rejected.copy()
            rejected.insert(0, "selection_date", selection_date)
            rejection_rows.extend(rejected.to_dict("records"))
    return (
        pd.DataFrame(preview_rows),
        pd.DataFrame(rejection_rows),
        pd.DataFrame(concentration_rows),
    )
