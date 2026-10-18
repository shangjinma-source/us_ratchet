"""Reconstructed research migration gate for reviewed-calendar runtime v3.

The predecessor is verified only for immutable code, contracts, and historical
ledger prefix.  Its obsolete current-vendor-calendar gate is never invoked.
New adapter tests are executed against their hash-bound source tree; a passing
gate permits a migration review, not task registration or live promotion.
Actual Scheduled Task smoke remains a separate mandatory acceptance step.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

import yaml

from backtest.ndx_dynamic_shadow_activation_v3 import verify_activation_v3_static_sources
from backtest.ndx_observed_session_calendar_v2 import verify_canonical_reviewed_calendar_v2

MANIFEST = Path("data/cache/research/ndx_dynamic_shadow_activation_v4/manifest.json")
CALENDAR = Path("data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json")
PREDECESSOR = Path("data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json")
CONTRACT = Path("config/ndx_dynamic_shadow_runner_v3.yaml")
STATUS = "READY_FOR_RESEARCH_RUNTIME_V3_MIGRATION_REVIEW_ONLY"
MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "generated_at_utc", "status",
    "predecessor_static_manifest_sha256", "runner_contract", "sources",
    "runtime_proofs", "calendar_event_prefix_file_sha256", "boundaries",
    "manifest_sha256",
}
TEST_SUITES = (
    "test_ndx_observed_session_calendar_v2.py",
    "test_ndx_observed_session_calendar_v2_adversarial.py",
    "test_ndx_dynamic_shadow_candidate_generator_v2.py",
    "test_ndx_dynamic_shadow_fresh_search_v3.py",
    "test_ndx_dynamic_shadow_daily_v2.py",
    "test_ndx_dynamic_shadow_daily_v3.py",
    "test_ndx_dynamic_shadow_activation_v4.py",
)
RUNTIME_DEPENDENCIES = (
    "backtest/ndx_dynamic_shadow_activation_v2.py",
    "backtest/ndx_dynamic_shadow_activation_v3.py",
    "backtest/ndx_cardinality_discovery.py",
    "backtest/ndx_dynamic_shadow_activation_readiness.py",
    "backtest/ndx_dynamic_shadow_runner.py",
    "backtest/ndx_dynamic_shadow_selector_registry.py",
    "backtest/ndx_original8_control.py",
    "backtest/ndx_portfolio_objective.py",
    "backtest/ndx_whole_lot_rebalance.py",
    "backtest/weights.py", "core/config.py", "core/helpers.py",
    "data/candidate_pool.py", "data/fetch.py", "data/funds.py",
    "data/ndx_history.py", "data/ndx_price_basis.py",
    "data/ndx_security_identity.py", "data/providers.py", "data/versioning.py",
)
SOURCES = (
    "config/ndx_dynamic_shadow_runner_v3.yaml",
    "backtest/ndx_observed_session_calendar_v2.py",
    "scripts/ndx_observed_session_calendar_v2.py",
    "backtest/ndx_dynamic_shadow_candidate_calendar_v2.py",
    "scripts/ndx_dynamic_shadow_candidate_generator_v2.py",
    "scripts/ndx_dynamic_shadow_fresh_search_v3.py",
    "backtest/ndx_dynamic_shadow_daily_v2.py",
    "scripts/ndx_dynamic_shadow_daily_v3.py",
    "backtest/ndx_dynamic_shadow_activation_v4.py",
    "scripts/ndx_dynamic_shadow_activation_v4.py",
) + RUNTIME_DEPENDENCIES + tuple("tests/" + name for name in TEST_SUITES)
BOUNDARIES = {
    "research_only": True, "task_registration_performed": False,
    "task_smoke_required_after_cutover": True, "promotion_allowed": False,
    "live_mutation_allowed": False, "parallel_old_new_tasks_allowed": False,
    "current_v1_vendor_rows_required": False,
}


class ActivationV4Error(ValueError):
    pass


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Hash raw bytes without trusting any repository-provided hash helper."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sources(root: Path) -> dict:
    return {name: {"path": (root / name).as_posix(), "sha256": file_sha256(root / name)}
            for name in SOURCES}


def _immutable_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".activation-v4-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # Hard-link creation is atomic and cannot overwrite an existing seal.
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ActivationV4Error(f"immutable activation artifact collision: {path.name}")
    finally:
        temporary.unlink(missing_ok=True)


def _validate_proofs(proofs: Any) -> None:
    if not isinstance(proofs, list) or [item.get("suite") for item in proofs] != list(TEST_SUITES):
        raise ActivationV4Error("runtime proof suite coverage changed")
    if any(
        set(item) != {"suite", "tests", "verified_exit_code"}
        or type(item.get("tests")) is not int or item["tests"] <= 0
        or type(item.get("verified_exit_code")) is not int
        or item["verified_exit_code"] != 0
        for item in proofs
    ):
        raise ActivationV4Error("runtime proof result is incomplete")


def _contract(root: Path) -> dict:
    value = yaml.safe_load((root / CONTRACT).read_text(encoding="utf-8"))
    predecessor = value.get("predecessor") or {}
    if (
        value.get("schema_version") != 3
        or value.get("runner_id") != "ndx_dynamic_shadow_runner_v3"
        or value.get("status") != "ACTIVATION_V4_GATED_RESEARCH_ONLY"
        or predecessor != {
            "path": "config/ndx_dynamic_shadow_runner_v2.yaml",
            "sha256": file_sha256(root / "config/ndx_dynamic_shadow_runner_v2.yaml"),
            "inherit_strategy_schedule_execution_and_evidence_contracts": True,
            "strategy_or_dynamic_k_semantics_changed": False,
        }
    ):
        raise ActivationV4Error("runner v3 predecessor contract changed")
    expected = {
        "calendar_manifest": CALENDAR.as_posix(),
        "calendar_script": "scripts/ndx_observed_session_calendar_v2.py",
        "candidate_script": "scripts/ndx_dynamic_shadow_candidate_generator_v2.py",
        "fresh_search_script": "scripts/ndx_dynamic_shadow_fresh_search_v3.py",
        "daily_script": "scripts/ndx_dynamic_shadow_daily_v3.py",
        "daily_adapter": "backtest/ndx_dynamic_shadow_daily_v2.py",
        "activation_manifest": MANIFEST.as_posix(),
        "preserve_append_only_output_namespaces": True,
        "initialize_calendar_implicitly": False,
        "current_v1_calendar_verification_required": False,
        "immutable_v1_static_lineage_verification_required": True,
        "old_and_new_tasks_parallel_allowed": False,
        "promotion_allowed": False, "live_mutation_allowed": False,
    }
    if set(value) != {"schema_version", "runner_id", "status", "predecessor", "runtime_overrides"} or value["runtime_overrides"] != expected:
        raise ActivationV4Error("runner v3 runtime contract changed")
    return value


def _runtime_proofs(root: Path) -> list[dict]:
    before = _sources(root)
    proofs = []
    for name in TEST_SUITES:
        process = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", name, "-q"],
            cwd=root, text=True, capture_output=True, timeout=120,
        )
        output = process.stdout + process.stderr
        match = re.search(r"Ran (\d+) tests? in", output)
        if process.returncode or match is None or int(match.group(1)) == 0:
            raise ActivationV4Error(f"runtime proof failed or discovered no tests: {name}\n{output[-4000:]}")
        proofs.append({"suite": name, "tests": int(match.group(1)), "verified_exit_code": 0})
    if _sources(root) != before:
        raise ActivationV4Error("runtime source tree changed during proof execution")
    _validate_proofs(proofs)
    return proofs


def verify_activation_v4_static_sources(path: str | Path, *, repository_root: str | Path) -> dict:
    root = Path(repository_root).resolve()
    path = Path(path).resolve()
    if path != (root / MANIFEST).resolve():
        raise ActivationV4Error("activation v4 path is not canonical")
    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    declared = unsigned.pop("manifest_sha256", None)
    if (
        set(payload) != MANIFEST_FIELDS or payload.get("schema_version") != 1
        or declared != _hash(unsigned) or payload.get("status") != STATUS
        or payload.get("manifest_type") != "ndx_dynamic_shadow_activation_v4"
        or payload.get("boundaries") != BOUNDARIES
        or payload.get("sources") != _sources(root)
        or payload.get("runner_contract") != _contract(root)
        or payload.get("predecessor_static_manifest_sha256") != file_sha256(root / PREDECESSOR)
    ):
        raise ActivationV4Error("activation v4 identity, sources, or boundaries changed")
    verify_activation_v3_static_sources(root / PREDECESSOR, repository_root=root)
    _validate_proofs(payload.get("runtime_proofs"))
    prefix_path = path.parent / "calendar_event_prefix.json"
    if file_sha256(prefix_path) != payload.get("calendar_event_prefix_file_sha256"):
        raise ActivationV4Error("activation v4 frozen calendar prefix changed")
    return payload


def verify_activation_v4_manifest(path: str | Path, *, repository_root: str | Path) -> dict:
    root = Path(repository_root).resolve()
    payload = verify_activation_v4_static_sources(path, repository_root=root)
    calendar = verify_canonical_reviewed_calendar_v2(root / CALENDAR, repository_root=root)
    prefix = json.loads((root / MANIFEST.parent / "calendar_event_prefix.json").read_text(encoding="utf-8"))
    if not isinstance(prefix, list) or not prefix or list(calendar.events)[:len(prefix)] != prefix:
        raise ActivationV4Error("reviewed calendar no longer extends its activation prefix")
    if _runtime_proofs(root) != payload.get("runtime_proofs"):
        raise ActivationV4Error("runtime proof inventory changed")
    verify_activation_v4_static_sources(path, repository_root=root)
    calendar = verify_canonical_reviewed_calendar_v2(root / CALENDAR, repository_root=root)
    if list(calendar.events)[:len(prefix)] != prefix:
        raise ActivationV4Error("reviewed calendar prefix changed during runtime proofs")
    return payload


def build_activation_v4_manifest(repository_root: str | Path) -> dict:
    root = Path(repository_root).resolve()
    path = root / MANIFEST
    if path.exists():
        return verify_activation_v4_manifest(path, repository_root=root)
    verify_activation_v3_static_sources(root / PREDECESSOR, repository_root=root)
    contract = _contract(root)
    calendar = verify_canonical_reviewed_calendar_v2(root / CALENDAR, repository_root=root)
    sources = _sources(root)
    predecessor_hash = file_sha256(root / PREDECESSOR)
    # Copy values before proofs: a verifier object must not be a mutable snapshot.
    prefix = json.loads(json.dumps(list(calendar.events)))
    proofs = _runtime_proofs(root)
    if sources != _sources(root):
        raise ActivationV4Error("source tree changed before activation freeze")
    verify_activation_v3_static_sources(root / PREDECESSOR, repository_root=root)
    calendar = verify_canonical_reviewed_calendar_v2(root / CALENDAR, repository_root=root)
    if (file_sha256(root / PREDECESSOR) != predecessor_hash
            or _contract(root) != contract
            or not prefix or list(calendar.events)[:len(prefix)] != prefix):
        raise ActivationV4Error("lineage or calendar changed before activation freeze")
    prefix_bytes = (json.dumps(prefix, sort_keys=True, indent=2) + "\n").encode()
    payload = {
        "schema_version": 1, "manifest_type": "ndx_dynamic_shadow_activation_v4",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": STATUS,
        "predecessor_static_manifest_sha256": predecessor_hash,
        "runner_contract": contract, "sources": sources, "runtime_proofs": proofs,
        "calendar_event_prefix_file_sha256": hashlib.sha256(prefix_bytes).hexdigest(),
        "boundaries": dict(BOUNDARIES),
    }
    payload["manifest_sha256"] = _hash(payload)
    # Publish the entire bundle with one rename. Interrupted staging directories
    # are diagnostic only; no partial canonical artifact can block a retry.
    path.parent.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".activation-v4-bundle-", dir=path.parent.parent))
    prefix_path = staging / "calendar_event_prefix.json"
    _immutable_bytes(prefix_path, prefix_bytes)
    _immutable_bytes(staging / path.name, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
    if path.parent.exists():
        raise ActivationV4Error("canonical activation bundle appeared before publication")
    os.rename(staging, path.parent)
    return verify_activation_v4_manifest(path, repository_root=root)
