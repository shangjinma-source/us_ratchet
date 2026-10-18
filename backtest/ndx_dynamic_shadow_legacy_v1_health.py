"""Read-only health classification for the retired dynamic-shadow v1 lineage.

This diagnostic deliberately separates two questions:

* can the legacy verifier still rebuild its mutable runtime inputs today; and
* are the immutable historical artifacts still useful as audit evidence?

A healthy result never grants task-registration, promotion, live mutation, or
order authority.  The replacement v3/v4 lineage has its own activation gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from backtest.ndx_dynamic_shadow_activation_readiness import (
    verify_observed_session_calendar_manifest,
)
from backtest.ndx_dynamic_shadow_activation_v2 import verify_activation_v2_manifest
from backtest.ndx_dynamic_shadow_runner import build_dynamic_shadow_readiness


HEALTHY_STATUS = "HEALTHY_LEGACY_V1_EVIDENCE_CHAIN_DIAGNOSTIC_ONLY"
DEGRADED_STATUS = "DEGRADED_LEGACY_V1_EVIDENCE_CHAIN_DIAGNOSTIC_ONLY"


def _check(passed: bool, reason: str | None, **details: Any) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "reason": None if passed else str(reason or "unspecified legacy health failure"),
        **details,
    }


def build_legacy_v1_health(
    repository_root: str | Path,
    *,
    calendar_verifier: Callable[[Path, Path], Mapping[str, Any]]
    = verify_observed_session_calendar_manifest,
    activation_verifier: Callable[..., Mapping[str, Any]] = verify_activation_v2_manifest,
    runner_readiness_builder: Callable[..., Mapping[str, Any]]
    = build_dynamic_shadow_readiness,
    registration_probe: Callable[[Path], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return current legacy health without converting it into authority."""

    root = Path(repository_root).resolve()
    calendar_path = (
        root / "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
    ).resolve()
    activation_path = (
        root / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
    ).resolve()
    runner_contract = (root / "config/ndx_dynamic_shadow_runner_v1.yaml").resolve()

    try:
        calendar = dict(calendar_verifier(calendar_path, root))
        calendar_passed = calendar.get("verified") is True
        calendar_reason = calendar.get("error")
    except Exception as exc:  # defensive diagnostic boundary
        calendar = {}
        calendar_passed = False
        calendar_reason = f"{type(exc).__name__}: {exc}"

    try:
        activation = dict(activation_verifier(activation_path, repository_root=root))
        activation_passed = (
            activation.get("status") == "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION"
        )
        activation_reason = None if activation_passed else "legacy activation status is not ready"
    except Exception as exc:
        activation = {}
        activation_passed = False
        activation_reason = f"{type(exc).__name__}: {exc}"

    try:
        runner = dict(runner_readiness_builder(
            runner_contract,
            as_of_date=datetime.now(timezone.utc).date().isoformat(),
        ))
        observed = runner.get("observed_session_calendar") or {}
        runner_passed = (
            isinstance(observed, Mapping)
            and observed.get("verified") is True
            and not any(
                item.get("blocker_id")
                == "VERIFIED_US_SESSION_CALENDAR_MANIFEST_MISSING_OR_INVALID"
                for item in (runner.get("blockers") or [])
                if isinstance(item, Mapping)
            )
        )
        runner_reason = None if runner_passed else str(
            observed.get("error") or "legacy runner calendar gate is blocked"
        )
        runner_execution_ready = bool(
            runner.get("ready_for_decision_registration") is True
            and runner.get("ready_for_path_evaluation") is True
            and not (runner.get("blockers") or [])
        )
    except Exception as exc:
        runner = {}
        runner_passed = False
        runner_execution_ready = False
        runner_reason = f"{type(exc).__name__}: {exc}"

    if registration_probe is None:
        registration = {
            "passed": False,
            "reason": "legacy registration evidence was not probed",
            "returncode": None,
            "probed": False,
        }
    else:
        try:
            raw_registration = dict(registration_probe(root))
            registration = {
                "passed": raw_registration.get("passed") is True,
                "reason": raw_registration.get("reason"),
                "returncode": raw_registration.get("returncode"),
                "probed": True,
            }
            if not registration["passed"] and not registration["reason"]:
                registration["reason"] = "legacy registration evidence did not verify"
        except Exception as exc:
            registration = {
                "passed": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "returncode": None,
                "probed": True,
            }

    checks = {
        "observed_calendar_v1_current_runtime": _check(
            calendar_passed, calendar_reason,
            manifest_path=calendar_path.as_posix(),
            reported_manifest_sha256=calendar.get("manifest_sha256"),
        ),
        "activation_v2_current_runtime": _check(
            activation_passed, activation_reason,
            manifest_path=activation_path.as_posix(),
        ),
        "runner_v1_current_calendar_gate": _check(
            runner_passed, runner_reason,
            contract_path=runner_contract.as_posix(),
            readiness_status=runner.get("status"),
        ),
        "selection_task_registration_v1_current_runtime": registration,
    }
    evidence_chain_reproducible = all(
        item.get("passed") is True for item in checks.values()
    )
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_legacy_v1_health",
        "health_scope": "legacy_calendar_and_activation_evidence_only",
        "status": (
            HEALTHY_STATUS if evidence_chain_reproducible else DEGRADED_STATUS
        ),
        "checks": checks,
        "legacy_evidence_chain_currently_reproducible": evidence_chain_reproducible,
        "runner_execution_ready": runner_execution_ready,
        "historical_artifact_deletion_or_rewrite_allowed": False,
        "replacement_lineage": "DYNAMIC_SHADOW_RUNTIME_V3_ACTIVATION_V4",
        "new_runtime_requires_current_v1_vendor_rows": False,
        "authoritative_for_task_registration": False,
        "research_automation_registration_allowed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "state_mutation_allowed": False,
        "broker_snapshot_mutation_allowed": False,
        "today_advice_mutation_allowed": False,
        "order_creation_allowed": False,
    }


__all__ = [
    "DEGRADED_STATUS",
    "HEALTHY_STATUS",
    "build_legacy_v1_health",
]
