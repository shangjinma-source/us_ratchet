"""Plan-only deadline budget for prospective dynamic-shadow search shards.

This module deliberately does not execute search or certify checkpoints.  It is
an immutable-input planning contract for the next version of the executor.  A
checkpoint may be supplied here only after the active executor has already
verified it against the sealed snapshot and coordinate identity.
"""

from __future__ import annotations

from datetime import datetime
from math import ceil, isfinite
from typing import Any, Iterable, Mapping, Sequence


EXACT = "EXACT_ENUMERATION"
BOUNDED = "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"
SEARCH_CLASSES = {EXACT, BOUNDED}


class NdxDynamicShadowSearchBudgetError(ValueError):
    """Raised when a budget or resume input is not internally trustworthy."""


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise NdxDynamicShadowSearchBudgetError(f"{label} must be timezone-aware")
    return value


def _positive_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowSearchBudgetError(f"{label} must be numeric") from exc
    if not isfinite(number) or number <= 0:
        raise NdxDynamicShadowSearchBudgetError(f"{label} must be positive")
    return number


def _normalize_jobs(job_plan: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    required = {
        "checkpoint_key",
        "universe_track",
        "holding_count",
        "job_search_class",
        "theoretical_issuer_combinations",
    }
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in job_plan:
        missing = required - set(raw)
        if missing:
            raise NdxDynamicShadowSearchBudgetError(
                f"job is missing required fields: {sorted(missing)}"
            )
        key = str(raw["checkpoint_key"])
        if not key or key in seen:
            raise NdxDynamicShadowSearchBudgetError(
                "checkpoint keys must be non-empty and unique"
            )
        seen.add(key)
        search_class = str(raw["job_search_class"])
        if search_class not in SEARCH_CLASSES:
            raise NdxDynamicShadowSearchBudgetError(
                f"unknown job_search_class: {search_class}"
            )
        holding_count = int(raw["holding_count"])
        combinations = int(raw["theoretical_issuer_combinations"])
        if holding_count < 1 or combinations < 1:
            raise NdxDynamicShadowSearchBudgetError(
                "holding_count and theoretical combinations must be positive"
            )
        jobs.append(
            {
                "checkpoint_key": key,
                "universe_track": str(raw["universe_track"]),
                "holding_count": holding_count,
                "job_search_class": search_class,
                "theoretical_issuer_combinations": combinations,
            }
        )
    if not jobs:
        raise NdxDynamicShadowSearchBudgetError("job plan cannot be empty")
    return jobs


def estimate_shard_budget_seconds(
    job: Mapping[str, Any],
    *,
    exact_combinations_per_second_floor: float,
    exact_fixed_overhead_seconds: int,
    bounded_shard_budget_seconds: int,
    uncertainty_multiplier: float,
    minimum_shard_start_budget_seconds: int,
) -> int:
    """Return a conservative admission estimate, never a completion claim."""

    rate = _positive_number(
        exact_combinations_per_second_floor,
        "exact_combinations_per_second_floor",
    )
    multiplier = _positive_number(uncertainty_multiplier, "uncertainty_multiplier")
    fixed = int(_positive_number(exact_fixed_overhead_seconds, "exact_fixed_overhead_seconds"))
    bounded = int(_positive_number(bounded_shard_budget_seconds, "bounded_shard_budget_seconds"))
    minimum = int(
        _positive_number(minimum_shard_start_budget_seconds, "minimum_shard_start_budget_seconds")
    )
    search_class = str(job["job_search_class"])
    if search_class == EXACT:
        base = fixed + int(ceil(int(job["theoretical_issuer_combinations"]) / rate))
    elif search_class == BOUNDED:
        base = bounded
    else:
        raise NdxDynamicShadowSearchBudgetError(f"unknown job_search_class: {search_class}")
    return max(minimum, int(ceil(base * multiplier)))


def build_deadline_budget_plan(
    job_plan: Sequence[Mapping[str, Any]],
    *,
    verified_completed_checkpoint_keys: Iterable[str],
    now_utc: datetime,
    role_seal_deadline_utc: datetime,
    role_seal_reserve_seconds: int = 900,
    exact_combinations_per_second_floor: float = 25.0,
    exact_fixed_overhead_seconds: int = 30,
    bounded_shard_budget_seconds: int = 240,
    uncertainty_multiplier: float = 1.5,
    minimum_shard_start_budget_seconds: int = 60,
) -> dict[str, Any]:
    """Build a fail-closed shard admission and resume plan.

    ``verified_completed_checkpoint_keys`` is intentionally named: callers must
    not pass directory existence or an unverified self-report.  The future
    active integration must source it from the executor's checkpoint verifier.
    """

    now = _aware(now_utc, "now_utc")
    deadline = _aware(role_seal_deadline_utc, "role_seal_deadline_utc")
    if int(role_seal_reserve_seconds) < 0:
        raise NdxDynamicShadowSearchBudgetError("role seal reserve cannot be negative")
    jobs = _normalize_jobs(job_plan)
    expected = {job["checkpoint_key"] for job in jobs}
    completed_list = [str(value) for value in verified_completed_checkpoint_keys]
    if len(completed_list) != len(set(completed_list)):
        raise NdxDynamicShadowSearchBudgetError("completed checkpoint keys contain duplicates")
    completed = set(completed_list)
    unexpected = completed - expected
    if unexpected:
        raise NdxDynamicShadowSearchBudgetError(
            f"completed checkpoint is not in sealed job plan: {sorted(unexpected)}"
        )

    seconds_to_deadline = max(0, int((deadline - now).total_seconds()))
    executable_seconds = max(0, seconds_to_deadline - int(role_seal_reserve_seconds))
    pending: list[dict[str, Any]] = []
    for ordinal, job in enumerate(jobs):
        if job["checkpoint_key"] in completed:
            continue
        estimate = estimate_shard_budget_seconds(
            job,
            exact_combinations_per_second_floor=exact_combinations_per_second_floor,
            exact_fixed_overhead_seconds=exact_fixed_overhead_seconds,
            bounded_shard_budget_seconds=bounded_shard_budget_seconds,
            uncertainty_multiplier=uncertainty_multiplier,
            minimum_shard_start_budget_seconds=minimum_shard_start_budget_seconds,
        )
        pending.append({**job, "plan_ordinal": ordinal, "estimated_budget_seconds": estimate})

    next_job = pending[0] if pending else None
    next_admitted = bool(next_job and next_job["estimated_budget_seconds"] <= executable_seconds)
    all_complete = not pending and completed == expected
    before_deadline = now < deadline
    aggregation_allowed = all_complete
    role_seal_allowed = all_complete and before_deadline

    if all_complete and before_deadline:
        status = "ALL_SHARDS_VERIFIED_ROLE_SEAL_ALLOWED"
    elif all_complete:
        status = "ALL_SHARDS_VERIFIED_ROLE_SEAL_DEADLINE_MISSED"
    elif not before_deadline:
        status = "INCOMPLETE_DEADLINE_PASSED_NO_FALSE_COMPLETE"
    elif not next_admitted:
        status = "INCOMPLETE_DEADLINE_GUARD_NO_FALSE_COMPLETE"
    else:
        status = "NEXT_SHARD_ADMITTED_PLAN_ONLY"

    return {
        "manifest_type": "ndx_dynamic_shadow_search_budget_plan",
        "schema_version": 1,
        "status": status,
        "activation_status": "PLAN_ONLY_NOT_ACTIVATED",
        "portfolio_track": "portfolio_optimization",
        "migration_control_used_as_structure_answer": False,
        "planned_shard_count": len(jobs),
        "verified_completed_shard_count": len(completed),
        "pending_shard_count": len(pending),
        "seconds_to_role_seal_deadline": seconds_to_deadline,
        "role_seal_reserve_seconds": int(role_seal_reserve_seconds),
        "executable_seconds_before_reserve": executable_seconds,
        "next_shard": next_job,
        "next_shard_admitted": next_admitted,
        "aggregation_allowed": aggregation_allowed,
        "role_seal_allowed": role_seal_allowed,
        "partial_or_timed_out_shard_completion_claimed": False,
        "resume_source_requirement": "EXECUTOR_VERIFIED_COMPLETED_CHECKPOINTS_ONLY",
        "future_activation_version_migration_required": True,
        "promotion_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "BOUNDED",
    "EXACT",
    "NdxDynamicShadowSearchBudgetError",
    "build_deadline_budget_plan",
    "estimate_shard_budget_seconds",
]
