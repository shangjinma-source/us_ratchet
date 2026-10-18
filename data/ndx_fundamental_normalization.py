"""Point-in-time normalization of SEC Company Facts for NDX research.

This module produces auditable statement values and ratio inputs. It does not
rank securities or authorize factor scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from data.ndx_fundamentals import METRIC_CONCEPTS, NdxFundamentalError


NORMALIZATION_POLICY_ID = "sec_companyfacts_pit_normalization_v1"
FLOW_METRICS = (
    "revenue",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "research_and_development",
)
INSTANT_METRICS = ("assets", "equity", "cash")
PENDING_POLICY_METRICS = ("debt", "shares_outstanding")
DERIVED_FACTORS = (
    "revenue_growth",
    "operating_margin",
    "net_margin",
    "free_cash_flow_margin",
    "operating_cash_flow_to_assets",
    "equity_to_assets",
    "cash_to_assets",
    "research_and_development_intensity",
)


@dataclass(frozen=True)
class NormalizationPolicy:
    annual_min_days: int = 330
    annual_max_days: int = 400
    ytd_min_days: int = 60
    ytd_max_days: int = 329
    direct_quarter_min_days: int = 60
    direct_quarter_max_days: int = 120
    fiscal_start_tolerance_days: int = 10
    comparable_duration_tolerance_days: int = 15
    comparable_year_tolerance_days: int = 30
    quarter_gap_tolerance_days: int = 15
    high_confidence_age_days: int = 200
    maximum_age_days: int = 550

    def validate(self) -> None:
        values = self.__dict__
        if any(int(value) < 0 for value in values.values()):
            raise NdxFundamentalError("normalization policy values must be nonnegative")
        if self.annual_min_days >= self.annual_max_days:
            raise NdxFundamentalError("annual duration bounds are invalid")
        if self.ytd_min_days >= self.ytd_max_days:
            raise NdxFundamentalError("YTD duration bounds are invalid")
        if self.high_confidence_age_days > self.maximum_age_days:
            raise NdxFundamentalError("confidence age exceeds maximum age")


@dataclass(frozen=True)
class _Fact:
    cik: int
    metric: str
    namespace: str
    concept: str
    concept_priority: int
    unit: str
    value: float
    form: str
    available_date: date
    period_start: date | None
    period_end: date
    duration_days: int | None
    accession_number: str
    frame: str

    @property
    def revision_key(self) -> tuple:
        return (
            self.namespace,
            self.concept,
            self.unit,
            self.period_start,
            self.period_end,
        )


@dataclass(frozen=True)
class _Candidate:
    metric: str
    value: float
    unit: str
    method: str
    period_start: date | None
    period_end: date
    concept_priority: int
    components: tuple[tuple[str, float, _Fact], ...]


def _concept_priority_map() -> dict[tuple[str, str, str], int]:
    priorities = {}
    for metric, namespaces in METRIC_CONCEPTS.items():
        offset = 0
        for namespace, concepts in namespaces.items():
            for position, concept in enumerate(concepts):
                priorities[(metric, namespace, concept)] = offset + position
            offset += len(concepts)
    return priorities


CONCEPT_PRIORITIES = _concept_priority_map()


def _as_date(value) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _prepare_facts(records: pd.DataFrame) -> list[_Fact]:
    required = {
        "cik",
        "metric",
        "namespace",
        "concept",
        "unit",
        "value",
        "form",
        "available_date",
        "period_start",
        "period_end",
        "accession_number",
        "frame",
    }
    missing = sorted(required - set(records.columns))
    if missing:
        raise NdxFundamentalError(
            f"normalization source columns missing: {missing}; rebuild readiness offline"
        )
    facts = []
    for row in records.itertuples(index=False):
        metric = str(row.metric)
        priority = CONCEPT_PRIORITIES.get(
            (metric, str(row.namespace), str(row.concept))
        )
        if priority is None or metric in PENDING_POLICY_METRICS:
            continue
        available = _as_date(row.available_date)
        period_end = _as_date(row.period_end)
        period_start = _as_date(row.period_start)
        value = pd.to_numeric(row.value, errors="coerce")
        if (
            available is None
            or period_end is None
            or pd.isna(value)
            or not np.isfinite(value)
        ):
            continue
        duration = (
            (period_end - period_start).days + 1
            if period_start is not None else None
        )
        facts.append(_Fact(
            cik=int(row.cik),
            metric=metric,
            namespace=str(row.namespace),
            concept=str(row.concept),
            concept_priority=int(priority),
            unit=str(row.unit),
            value=float(value),
            form=str(row.form),
            available_date=available,
            period_start=period_start,
            period_end=period_end,
            duration_days=duration,
            accession_number=(
                "" if pd.isna(row.accession_number)
                else str(row.accession_number)
            ),
            frame="" if pd.isna(row.frame) else str(row.frame),
        ))
    return sorted(
        facts,
        key=lambda item: (
            item.cik,
            item.metric,
            item.available_date,
            item.accession_number,
            item.form,
        ),
    )


def _candidate_key(candidate: _Candidate) -> tuple:
    method_rank = {
        "annual": 1,
        "direct_four_quarters": 2,
        "annual_plus_ytd": 3,
        "instant_latest": 3,
    }
    common = (
        candidate.period_end.toordinal(),
        method_rank.get(candidate.method, 0),
        1 if candidate.unit == "USD" else 0,
    )
    if candidate.metric == "revenue":
        # Multiple standard revenue concepts can coexist for a total and a
        # narrower activity. Within one currency and period, total revenue is
        # the largest positive candidate; concept priority only breaks ties.
        return common + (
            candidate.value if candidate.value > 0 else float("-inf"),
            -candidate.concept_priority,
            candidate.unit,
        )
    return common + (
        -candidate.concept_priority,
        candidate.unit,
    )


def _annual_plus_ytd_candidates(
    metric: str,
    facts: list[_Fact],
    policy: NormalizationPolicy,
) -> list[_Candidate]:
    out = []
    annual = [
        fact for fact in facts
        if fact.duration_days is not None
        and policy.annual_min_days <= fact.duration_days <= policy.annual_max_days
    ]
    ytd = [
        fact for fact in facts
        if fact.duration_days is not None
        and policy.ytd_min_days <= fact.duration_days <= policy.ytd_max_days
    ]
    for annual_fact in annual:
        out.append(_Candidate(
            metric=metric,
            value=annual_fact.value,
            unit=annual_fact.unit,
            method="annual",
            period_start=annual_fact.period_start,
            period_end=annual_fact.period_end,
            concept_priority=annual_fact.concept_priority,
            components=(("annual", 1.0, annual_fact),),
        ))
        if annual_fact.period_start is None:
            continue
        current_rows = [
            fact for fact in ytd
            if fact.period_start is not None
            and 1 <= (fact.period_start - annual_fact.period_end).days
            <= policy.fiscal_start_tolerance_days
            and fact.period_end > annual_fact.period_end
        ]
        for current in current_rows:
            prior_rows = [
                fact for fact in ytd
                if fact.period_start is not None
                and abs((fact.period_start - annual_fact.period_start).days)
                <= policy.fiscal_start_tolerance_days
                and abs(int(fact.duration_days) - int(current.duration_days))
                <= policy.comparable_duration_tolerance_days
                and abs((current.period_end - fact.period_end).days - 365)
                <= policy.comparable_year_tolerance_days
            ]
            if not prior_rows:
                continue
            prior = max(
                prior_rows,
                key=lambda item: (
                    item.period_end,
                    item.available_date,
                    item.accession_number,
                ),
            )
            value = annual_fact.value + current.value - prior.value
            if not np.isfinite(value):
                continue
            out.append(_Candidate(
                metric=metric,
                value=float(value),
                unit=annual_fact.unit,
                method="annual_plus_ytd",
                period_start=annual_fact.period_start,
                period_end=current.period_end,
                concept_priority=annual_fact.concept_priority,
                components=(
                    ("annual", 1.0, annual_fact),
                    ("current_ytd", 1.0, current),
                    ("prior_ytd", -1.0, prior),
                ),
            ))
    return out


def _direct_quarter_candidates(
    metric: str,
    facts: list[_Fact],
    policy: NormalizationPolicy,
) -> list[_Candidate]:
    direct = [
        fact for fact in facts
        if fact.duration_days is not None
        and policy.direct_quarter_min_days
        <= fact.duration_days <= policy.direct_quarter_max_days
    ]
    by_end = {}
    for fact in direct:
        current = by_end.get(fact.period_end)
        if current is None or (
            fact.available_date,
            -abs(int(fact.duration_days) - 91),
            fact.accession_number,
        ) > (
            current.available_date,
            -abs(int(current.duration_days) - 91),
            current.accession_number,
        ):
            by_end[fact.period_end] = fact
    ordered = sorted(by_end.values(), key=lambda item: item.period_end)
    out = []
    for position in range(3, len(ordered)):
        window = ordered[position - 3:position + 1]
        if any(
            previous.period_start is None
            or current.period_start is None
            or not 0 <= (current.period_start - previous.period_end).days
            <= policy.quarter_gap_tolerance_days
            for previous, current in zip(window, window[1:])
        ):
            continue
        span = (window[-1].period_end - window[0].period_start).days + 1
        if not policy.annual_min_days <= span <= policy.annual_max_days:
            continue
        value = float(sum(item.value for item in window))
        if not np.isfinite(value):
            continue
        out.append(_Candidate(
            metric=metric,
            value=value,
            unit=window[0].unit,
            method="direct_four_quarters",
            period_start=window[0].period_start,
            period_end=window[-1].period_end,
            concept_priority=window[0].concept_priority,
            components=tuple(
                (f"quarter_{index}", 1.0, fact)
                for index, fact in enumerate(window, start=1)
            ),
        ))
    return out


def _normalize_flow(
    metric: str,
    state: Iterable[_Fact],
    policy: NormalizationPolicy,
) -> tuple[_Candidate | None, list[_Candidate]]:
    families: dict[tuple[str, str, str], list[_Fact]] = {}
    for fact in state:
        if fact.period_start is None:
            continue
        families.setdefault(
            (fact.namespace, fact.concept, fact.unit), []
        ).append(fact)
    candidates = []
    for facts in families.values():
        candidates.extend(_annual_plus_ytd_candidates(metric, facts, policy))
        candidates.extend(_direct_quarter_candidates(metric, facts, policy))
    return (
        max(candidates, key=_candidate_key) if candidates else None,
        candidates,
    )


def _candidate_concept_key(candidate: _Candidate) -> tuple[str, str]:
    fact = candidate.components[0][2]
    return fact.namespace, fact.concept


def _prior_year_candidate(
    current: _Candidate,
    candidates: Iterable[_Candidate],
) -> _Candidate | None:
    current_concept = _candidate_concept_key(current)
    eligible = []
    for candidate in candidates:
        gap_days = (current.period_end - candidate.period_end).days
        if (
            330 <= gap_days <= 400
            and candidate.unit == current.unit
            and _candidate_concept_key(candidate) == current_concept
        ):
            eligible.append((candidate, gap_days))
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (
            -abs(item[1] - 365),
            _candidate_key(item[0]),
        ),
    )[0]


def _normalize_instant(metric: str, state: Iterable[_Fact]) -> _Candidate | None:
    candidates = []
    for fact in state:
        if fact.period_start is not None:
            continue
        candidates.append(_Candidate(
            metric=metric,
            value=fact.value,
            unit=fact.unit,
            method="instant_latest",
            period_start=None,
            period_end=fact.period_end,
            concept_priority=fact.concept_priority,
            components=(("instant", 1.0, fact),),
        ))
    return max(candidates, key=_candidate_key) if candidates else None


def _normalization_cache(
    plan: pd.DataFrame,
    records: pd.DataFrame,
    policy: NormalizationPolicy,
) -> dict[tuple[int, str, str], tuple[_Candidate, _Candidate | None]]:
    facts = _prepare_facts(records)
    groups: dict[tuple[int, str], list[_Fact]] = {}
    for fact in facts:
        groups.setdefault((fact.cik, fact.metric), []).append(fact)
    dates_by_cik = {
        int(cik): sorted({str(value)[:10] for value in group["selection_date"]})
        for cik, group in plan.groupby("cik")
        if pd.notna(cik)
    }
    cache = {}
    for (cik, metric), source in groups.items():
        dates = dates_by_cik.get(cik, [])
        if not dates:
            continue
        source = sorted(
            source,
            key=lambda item: (
                item.available_date,
                item.accession_number,
                item.form,
            ),
        )
        state: dict[tuple, _Fact] = {}
        position = 0
        for selection_date in dates:
            cutoff = date.fromisoformat(selection_date)
            while (
                position < len(source)
                and source[position].available_date <= cutoff
            ):
                fact = source[position]
                state[fact.revision_key] = fact
                position += 1
            eligible = [
                fact for fact in state.values()
                if fact.period_end < cutoff
            ]
            comparison = None
            if metric in FLOW_METRICS:
                candidate, candidates = _normalize_flow(metric, eligible, policy)
                if metric == "revenue" and candidate is not None:
                    comparison = _prior_year_candidate(candidate, candidates)
            else:
                candidate = _normalize_instant(metric, eligible)
            if candidate is not None:
                cache[(cik, metric, selection_date)] = (candidate, comparison)
    return cache


def normalize_point_in_time_facts(
    plan: pd.DataFrame,
    records: pd.DataFrame,
    *,
    policy: NormalizationPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return normalized values, source components, and coverage summary."""
    selected_policy = policy or NormalizationPolicy()
    selected_policy.validate()
    required = {"selection_date", "ticker", "cik"}
    missing = sorted(required - set(plan.columns))
    if missing:
        raise NdxFundamentalError(f"normalization plan columns missing: {missing}")
    if plan["cik"].isna().any():
        raise NdxFundamentalError("normalization plan contains unmapped CIKs")
    base_plan = plan.drop_duplicates(["selection_date", "ticker"]).copy()
    base_plan["selection_date"] = base_plan["selection_date"].astype(str).str[:10]
    cache = _normalization_cache(base_plan, records, selected_policy)
    value_rows = []
    component_keys = set()
    component_rows = []
    for row in base_plan.itertuples(index=False):
        selection_date = str(row.selection_date)[:10]
        cutoff = date.fromisoformat(selection_date)
        for metric in METRIC_CONCEPTS:
            cached = cache.get((int(row.cik), metric, selection_date))
            candidate, comparison = cached if cached is not None else (None, None)
            if metric in PENDING_POLICY_METRICS:
                status = "policy_pending"
                candidate = None
                comparison = None
            elif candidate is None:
                status = "missing"
            else:
                age_days = (cutoff - candidate.period_end).days
                status = (
                    "normalized"
                    if age_days <= selected_policy.maximum_age_days
                    else "stale"
                )
            age_days = (
                (cutoff - candidate.period_end).days
                if candidate is not None else None
            )
            confidence = (
                "high"
                if age_days is not None
                and age_days <= selected_policy.high_confidence_age_days
                else "medium"
                if age_days is not None
                and age_days <= selected_policy.maximum_age_days
                else "rejected"
                if candidate is not None else "none"
            )
            component_sum = (
                sum(sign * fact.value for _, sign, fact in candidate.components)
                if candidate is not None else None
            )
            arithmetic_passed = bool(
                candidate is None
                or np.isclose(
                    candidate.value,
                    component_sum,
                    rtol=1e-12,
                    atol=1e-6,
                )
            )
            comparison_sum = (
                sum(sign * fact.value for _, sign, fact in comparison.components)
                if comparison is not None else None
            )
            comparison_arithmetic_passed = bool(
                comparison is None
                or np.isclose(
                    comparison.value,
                    comparison_sum,
                    rtol=1e-12,
                    atol=1e-6,
                )
            )
            future_guard_passed = bool(
                candidate is None
                or all(
                    fact.available_date <= cutoff and fact.period_end < cutoff
                    for _, _, fact in candidate.components
                )
            )
            comparison_future_guard_passed = bool(
                comparison is None
                or all(
                    fact.available_date <= cutoff and fact.period_end < cutoff
                    for _, _, fact in comparison.components
                )
            )
            value_rows.append({
                "selection_date": selection_date,
                "ticker": str(row.ticker).upper(),
                "cik": int(row.cik),
                "metric": metric,
                "status": status,
                "usable": status == "normalized",
                "confidence": confidence,
                "value": candidate.value if candidate is not None else None,
                "unit": candidate.unit if candidate is not None else None,
                "normalization_method": (
                    candidate.method if candidate is not None else None
                ),
                "period_start": (
                    candidate.period_start.isoformat()
                    if candidate is not None
                    and candidate.period_start is not None else None
                ),
                "period_end": (
                    candidate.period_end.isoformat()
                    if candidate is not None else None
                ),
                "age_days": age_days,
                "component_count": (
                    len(candidate.components) if candidate is not None else 0
                ),
                "concepts": (
                    ";".join(sorted({
                        f"{fact.namespace}:{fact.concept}"
                        for _, _, fact in candidate.components
                    })) if candidate is not None else None
                ),
                "source_available_date_max": (
                    max(
                        fact.available_date
                        for _, _, fact in candidate.components
                    ).isoformat() if candidate is not None else None
                ),
                "comparison_value": (
                    comparison.value if comparison is not None else None
                ),
                "comparison_unit": (
                    comparison.unit if comparison is not None else None
                ),
                "comparison_method": (
                    comparison.method if comparison is not None else None
                ),
                "comparison_period_end": (
                    comparison.period_end.isoformat()
                    if comparison is not None else None
                ),
                "comparison_gap_days": (
                    (candidate.period_end - comparison.period_end).days
                    if candidate is not None and comparison is not None else None
                ),
                "comparison_concepts": (
                    ";".join(sorted({
                        f"{fact.namespace}:{fact.concept}"
                        for _, _, fact in comparison.components
                    })) if comparison is not None else None
                ),
                "comparison_component_count": (
                    len(comparison.components) if comparison is not None else 0
                ),
                "comparison_source_available_date_max": (
                    max(
                        fact.available_date
                        for _, _, fact in comparison.components
                    ).isoformat() if comparison is not None else None
                ),
                "arithmetic_passed": bool(
                    arithmetic_passed and comparison_arithmetic_passed
                ),
                "future_data_guard_passed": bool(
                    future_guard_passed and comparison_future_guard_passed
                ),
            })
            if candidate is None:
                continue
            for component_set, selected in (
                ("current", candidate),
                ("prior_year", comparison),
            ):
                if selected is None:
                    continue
                component_key = (
                    int(row.cik), metric, selection_date, component_set
                )
                if component_key in component_keys:
                    continue
                component_keys.add(component_key)
                for component_order, (role, sign, fact) in enumerate(
                    selected.components, start=1
                ):
                    component_rows.append({
                    "selection_date": selection_date,
                    "cik": int(row.cik),
                    "metric": metric,
                    "component_set": component_set,
                    "normalization_method": selected.method,
                    "normalized_value": selected.value,
                    "normalized_unit": selected.unit,
                    "component_order": component_order,
                    "component_role": role,
                    "component_sign": sign,
                    "component_value": fact.value,
                    "signed_component_value": sign * fact.value,
                    "namespace": fact.namespace,
                    "concept": fact.concept,
                    "unit": fact.unit,
                    "form": fact.form,
                    "available_date": fact.available_date.isoformat(),
                    "period_start": (
                        fact.period_start.isoformat()
                        if fact.period_start is not None else None
                    ),
                    "period_end": fact.period_end.isoformat(),
                    "accession_number": fact.accession_number,
                    "frame": fact.frame,
                })
    values = pd.DataFrame(value_rows)
    components = pd.DataFrame(component_rows)
    summary = values.groupby(["selection_date", "metric"]).agg(
        universe_count=("ticker", "size"),
        normalized_count=("usable", "sum"),
        normalized_coverage=("usable", "mean"),
        high_confidence_count=(
            "confidence", lambda series: int(series.eq("high").sum())
        ),
        stale_count=("status", lambda series: int(series.eq("stale").sum())),
        missing_count=("status", lambda series: int(series.eq("missing").sum())),
        policy_pending_count=(
            "status", lambda series: int(series.eq("policy_pending").sum())
        ),
        age_days_p50=("age_days", "median"),
        age_days_p90=("age_days", lambda series: series.quantile(0.90)),
        arithmetic_passed=("arithmetic_passed", "all"),
        future_data_guard_passed=("future_data_guard_passed", "all"),
    ).reset_index()
    return values, components, summary


def _ratio_status(
    values: dict[str, float],
    units: dict[str, str],
    numerators: Iterable[str],
    denominator: str,
    *,
    require_nonnegative: Iterable[str] = (),
) -> tuple[float | None, str]:
    metrics = list(numerators) + [denominator]
    if any(metric not in values for metric in metrics):
        return None, "missing_component"
    if len({units.get(metric) for metric in metrics}) != 1:
        return None, "unit_mismatch"
    if values[denominator] <= 0:
        return None, "invalid_denominator"
    if any(values[metric] < 0 for metric in require_nonnegative):
        return None, "invalid_sign"
    numerator = sum(values[metric] for metric in numerators)
    value = numerator / values[denominator]
    return (float(value), "ready") if np.isfinite(value) else (None, "nonfinite")


def build_quality_factor_inputs(
    normalized_values: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build unranked, un-winsorized ratio inputs from usable normalized values."""
    required = {"selection_date", "ticker", "cik", "metric", "usable", "value", "unit"}
    missing = sorted(required - set(normalized_values.columns))
    if missing:
        raise NdxFundamentalError(f"normalized value columns missing: {missing}")
    identifiers = ["selection_date", "ticker", "cik"]
    base = normalized_values[identifiers].drop_duplicates().sort_values(identifiers)
    usable = normalized_values[normalized_values["usable"]].copy()
    value_map = {
        tuple(getattr(row, key) for key in identifiers) + (row.metric,): float(row.value)
        for row in usable.itertuples(index=False)
    }
    unit_map = {
        tuple(getattr(row, key) for key in identifiers) + (row.metric,): str(row.unit)
        for row in usable.itertuples(index=False)
    }
    revenue_comparisons = {}
    if {"comparison_value", "comparison_unit"}.issubset(usable.columns):
        revenue_comparisons = {
            tuple(getattr(row, key) for key in identifiers): (
                float(row.comparison_value),
                str(row.comparison_unit),
            )
            for row in usable[usable["metric"].eq("revenue")].itertuples(index=False)
            if pd.notna(row.comparison_value) and pd.notna(row.comparison_unit)
        }
    rows = []
    for item in base.itertuples(index=False):
        identity = (item.selection_date, item.ticker, int(item.cik))
        values = {
            metric: value_map[identity + (metric,)]
            for metric in FLOW_METRICS + INSTANT_METRICS
            if identity + (metric,) in value_map
        }
        units = {
            metric: unit_map[identity + (metric,)]
            for metric in FLOW_METRICS + INSTANT_METRICS
            if identity + (metric,) in unit_map
        }
        row = {
            "selection_date": item.selection_date,
            "ticker": item.ticker,
            "cik": int(item.cik),
        }
        for metric in FLOW_METRICS + INSTANT_METRICS:
            row[f"{metric}_value"] = values.get(metric)
            row[f"{metric}_unit"] = units.get(metric)
        comparison = revenue_comparisons.get(identity)
        row["revenue_comparison_value"] = (
            comparison[0] if comparison is not None else None
        )
        row["revenue_comparison_unit"] = (
            comparison[1] if comparison is not None else None
        )
        if "revenue" not in values or comparison is None:
            row["revenue_growth"] = None
            row["revenue_growth_status"] = "missing_component"
        elif units.get("revenue") != comparison[1]:
            row["revenue_growth"] = None
            row["revenue_growth_status"] = "unit_mismatch"
        elif comparison[0] <= 0:
            row["revenue_growth"] = None
            row["revenue_growth_status"] = "invalid_denominator"
        else:
            growth = values["revenue"] / comparison[0] - 1.0
            row["revenue_growth"] = float(growth) if np.isfinite(growth) else None
            row["revenue_growth_status"] = (
                "ready" if np.isfinite(growth) else "nonfinite"
            )
        factor_specs = {
            "operating_margin": (("operating_income",), "revenue", ()),
            "net_margin": (("net_income",), "revenue", ()),
            "free_cash_flow_margin": (
                ("operating_cash_flow", "capital_expenditure"),
                "revenue",
                ("capital_expenditure",),
            ),
            "operating_cash_flow_to_assets": (
                ("operating_cash_flow",), "assets", ()
            ),
            "equity_to_assets": (("equity",), "assets", ()),
            "cash_to_assets": (("cash",), "assets", ()),
            "research_and_development_intensity": (
                ("research_and_development",),
                "revenue",
                ("research_and_development",),
            ),
        }
        for factor, (numerators, denominator, nonnegative) in factor_specs.items():
            adjusted_values = dict(values)
            if factor == "free_cash_flow_margin" and all(
                metric in adjusted_values
                for metric in ("operating_cash_flow", "capital_expenditure")
            ):
                adjusted_values["capital_expenditure"] *= -1.0
                nonnegative = ()
                if values["capital_expenditure"] < 0:
                    row[factor] = None
                    row[f"{factor}_status"] = "invalid_sign"
                    continue
            value, status = _ratio_status(
                adjusted_values,
                units,
                numerators,
                denominator,
                require_nonnegative=nonnegative,
            )
            row[factor] = value
            row[f"{factor}_status"] = status
        row["factor_ready_count"] = sum(
            row[f"{factor}_status"] == "ready" for factor in DERIVED_FACTORS
        )
        rows.append(row)
    factors = pd.DataFrame(rows)
    coverage_rows = []
    for selection_date, group in factors.groupby("selection_date"):
        for factor in DERIVED_FACTORS:
            status = group[f"{factor}_status"]
            coverage_rows.append({
                "selection_date": selection_date,
                "factor": factor,
                "universe_count": len(group),
                "ready_count": int(status.eq("ready").sum()),
                "coverage": float(status.eq("ready").mean()),
                "missing_component_count": int(
                    status.eq("missing_component").sum()
                ),
                "unit_mismatch_count": int(status.eq("unit_mismatch").sum()),
                "invalid_denominator_count": int(
                    status.eq("invalid_denominator").sum()
                ),
                "invalid_sign_count": int(status.eq("invalid_sign").sum()),
            })
    return factors, pd.DataFrame(coverage_rows)
