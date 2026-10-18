"""Create-only research gate for candidate3/fresh4/daily4; never registers tasks.

Frozen predecessor sources remain mandatory. Mutable market inputs are checked
by their per-decision archives, not frozen here as permanent current snapshots.
Passing this gate is migration-review evidence, not an operational smoke test.
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

import yaml

from backtest.ndx_dynamic_shadow_activation_v4 import (
    SOURCES as PREDECESSOR_SOURCES, verify_activation_v4_static_sources,
)
from backtest.ndx_observed_session_calendar_v2 import verify_canonical_reviewed_calendar_v2

MANIFEST = Path("data/cache/research/ndx_dynamic_shadow_activation_v5/manifest.json")
PREDECESSOR = Path("data/cache/research/ndx_dynamic_shadow_activation_v4/manifest.json")
CALENDAR = Path("data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json")
CONTRACT = Path("config/ndx_dynamic_shadow_runner_v4.yaml")
STATUS = "READY_FOR_RESEARCH_RUNTIME_V4_MIGRATION_REVIEW_ONLY"
TEST_SUITES = (
    "test_ndx_dynamic_shadow_runner_v4_contract.py",
    "test_ndx_dynamic_shadow_candidate_identity_v3.py",
    "test_ndx_dynamic_shadow_candidate_membership_v3.py",
    "test_ndx_dynamic_shadow_candidate_generator_v3.py",
    "test_ndx_dynamic_shadow_candidate_generator_v3_adversarial.py",
    "test_ndx_dynamic_shadow_candidate_v3_public_verify.py",
    "test_ndx_candidate_v3_identity_csv.py",
    "test_ndx_upstream_identity_csv.py",
    "test_ndx_dynamic_shadow_fresh_search_v4.py",
    "test_ndx_dynamic_shadow_fresh_search_v4_executor.py",
    "test_ndx_dynamic_shadow_fresh_search_v4_e2e.py",
    "test_ndx_dynamic_shadow_fresh_search_v4_e2e_adversarial.py",
    "test_ndx_dynamic_shadow_fresh_search_v4_e2e_leading_zero.py",
    "test_ndx_dynamic_shadow_daily4_runtime_provenance.py",
    "test_ndx_dynamic_shadow_daily_v3_acceptance.py",
    "test_ndx_dynamic_shadow_daily_v4.py",
    "test_ndx_dynamic_shadow_daily_v4_real_guards.py",
    "test_ndx_dynamic_shadow_daily_v4_execution_e2e.py",
    "test_ndx_dynamic_shadow_daily_v4_cold_start.py",
    "test_ndx_dynamic_shadow_daily_economic_replay.py",
    "test_ndx_dynamic_shadow_activation_v5.py",
)
SOURCES = tuple(sorted(set(PREDECESSOR_SOURCES) | {
    CONTRACT.as_posix(), "config/ndx_dynamic_shadow_candidate_generator_v3.yaml",
    "config/ndx_dynamic_shadow_candidate_generator_v1.yaml",
    "config/candidate_taxonomy_v2.yaml",
    "config/ndx_cardinality_search_v1_plan.yaml", "config/ndx_security_lifecycle.yaml",
    "config/ndx_dynamic_shadow_fresh_search_v1.yaml",
    "config/ndx_dynamic_shadow_selector_registry_v1.yaml",
    "backtest/ndx_dynamic_shadow_activation_v5.py",
    "scripts/ndx_dynamic_shadow_activation_v5.py",
    "backtest/ndx_dynamic_shadow_candidate_generator_v3.py",
    "backtest/ndx_dynamic_shadow_candidate_membership_v3.py",
    "backtest/ndx_dynamic_shadow_candidate_identity_v3.py",
    "backtest/ndx_dynamic_shadow_candidate_snapshot.py",
    "scripts/ndx_dynamic_shadow_candidate_generator.py",
    "scripts/ndx_dynamic_shadow_candidate_generator_v3.py",
    "scripts/ndx_dynamic_shadow_fresh_search_v4.py",
    "scripts/ndx_dynamic_shadow_fresh_search_v2.py",
    "scripts/ndx_dynamic_shadow_fresh_search.py",
    "backtest/ndx_dynamic_shadow_fresh_search.py",
    "backtest/ndx_dynamic_shadow_fresh_search_v2.py",
    "backtest/ndx_dynamic_shadow_search_budget.py",
    "backtest/ndx_dynamic_candidate_policy.py",
    "backtest/ndx_dynamic_shadow_daily.py",
    "backtest/ndx_dynamic_shadow_daily_v3.py",
    "backtest/ndx_dynamic_shadow_daily_economic_replay.py",
    "scripts/ndx_dynamic_shadow_daily_v4.py",
    "data/ndx_taxonomy.py", "data/ndx_history_csv_v2.py",
    "data/ndx_filing_identity.py", "data/ndx_sic_history.py",
    "data/ndx_fundamentals.py", "data/cn_source.py",
    "core/__init__.py", "backtest/__init__.py",
    "data/__init__.py", "scripts/__init__.py",
    "tests/test_ndx_dynamic_shadow_fresh_search.py",
    # Runs the real gate, so bind its code but never recursively schedule it in proofs.
    "tests/test_ndx_activation_v5_boundary_integration.py",
    "scripts/ndx_taxonomy_v2.py", "tests/fixture_fresh_search_v4_e2e.py",
    "tests/fixture_daily_v4_cold_start.py",
} | {"tests/" + name for name in TEST_SUITES}))
BOUNDARIES = {
    "research_only": True, "task_registration_performed": False,
    "task_smoke_required_after_cutover": True, "promotion_allowed": False,
    "live_mutation_allowed": False, "parallel_old_new_tasks_allowed": False,
    "current_v1_vendor_rows_required": False,
    "acceptance_required_for_every_consumed_final": True,
    "acceptance_required_for_every_realized_batch": True,
}
MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "generated_at_utc", "status",
    "predecessor_static_manifest_sha256", "runner_contract", "sources",
    "runtime_proofs", "calendar_event_prefix_file_sha256", "boundaries", "manifest_sha256",
}


class ActivationV5Error(ValueError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sources(root):
    return {name: {"path": (root / name).as_posix(), "sha256": file_sha256(root / name)}
            for name in SOURCES}


def _contract(root):
    value = yaml.safe_load((root / CONTRACT).read_text(encoding="utf-8"))
    expected = {
        "schema_version": 4, "runner_id": "ndx_dynamic_shadow_runner_v4",
        "status": "ACTIVATION_V5_GATED_RESEARCH_ONLY",
        "predecessor": {
            "path": "config/ndx_dynamic_shadow_runner_v3.yaml",
            "sha256": file_sha256(root / "config/ndx_dynamic_shadow_runner_v3.yaml"),
            "inherit_strategy_schedule_execution_and_evidence_contracts": True,
            "strategy_or_dynamic_k_semantics_changed": False,
        },
        "runtime_overrides": {
            "calendar_manifest": CALENDAR.as_posix(),
            "calendar_script": "scripts/ndx_observed_session_calendar_v2.py",
            "candidate_script": "scripts/ndx_dynamic_shadow_candidate_generator_v3.py",
            "fresh_search_script": "scripts/ndx_dynamic_shadow_fresh_search_v4.py",
            "daily_script": "scripts/ndx_dynamic_shadow_daily_v4.py",
            "daily_adapter": "backtest/ndx_dynamic_shadow_daily_v3.py",
            "activation_manifest": MANIFEST.as_posix(),
            "acceptance_receipt_root": "data/cache/research/ndx_dynamic_shadow_fresh_search_v4_acceptance",
            "acceptance_required_for_every_consumed_final": True,
            "acceptance_required_for_every_realized_batch": True,
            "preserve_append_only_output_namespaces": True,
            "initialize_calendar_implicitly": False,
            "current_v1_calendar_verification_required": False,
            "immutable_v1_static_lineage_verification_required": True,
            "old_and_new_tasks_parallel_allowed": False,
            "promotion_allowed": False, "live_mutation_allowed": False,
        },
    }
    if _json(value) != _json(expected):
        raise ActivationV5Error("runner v4 contract changed")
    return value


def _validate_proofs(proofs):
    if not isinstance(proofs, list) or len(proofs) != len(TEST_SUITES):
        raise ActivationV5Error("runtime proof suite coverage changed")
    for item, suite in zip(proofs, TEST_SUITES):
        if (not isinstance(item, dict) or set(item) != {"suite", "tests", "verified_exit_code"}
                or item.get("suite") != suite or type(item.get("tests")) is not int
                or item["tests"] <= 0 or type(item.get("verified_exit_code")) is not int
                or item["verified_exit_code"] != 0):
            raise ActivationV5Error("runtime proof result incomplete")


def _evidence(root):
    verify_activation_v4_static_sources(root / PREDECESSOR, repository_root=root)
    calendar = verify_canonical_reviewed_calendar_v2(root / CALENDAR, repository_root=root)
    events = json.loads(_json(list(calendar.events)))
    if not events:
        raise ActivationV5Error("empty reviewed calendar")
    return {"sources": _sources(root), "contract": _contract(root),
            "predecessor": file_sha256(root / PREDECESSOR), "events": events}


def _runtime_proofs(root):
    before = _evidence(root)
    proofs = []
    for suite in TEST_SUITES:
        process = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", suite, "-q"],
            cwd=root, text=True, capture_output=True, timeout=180,
        )
        output = process.stdout + process.stderr
        match = re.search(r"Ran (\d+) tests? in", output)
        if process.returncode or match is None or int(match.group(1)) <= 0:
            raise ActivationV5Error(f"runtime proof failed: {suite}\n{output[-4000:]}")
        proofs.append({"suite": suite, "tests": int(match.group(1)), "verified_exit_code": 0})
    if _json(_evidence(root)) != _json(before):
        raise ActivationV5Error("source, lineage, contract or calendar changed during proofs")
    _validate_proofs(proofs)
    return proofs


def verify_activation_v5_static_sources(path, *, repository_root):
    root, path = Path(repository_root).resolve(), Path(path).resolve()
    if path != (root / MANIFEST).resolve():
        raise ActivationV5Error("activation v5 path is not canonical")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != MANIFEST_FIELDS:
        raise ActivationV5Error("activation v5 fields changed")
    unsigned = dict(payload)
    declared = unsigned.pop("manifest_sha256")
    if (type(payload["schema_version"]) is not int or payload["schema_version"] != 1
            or declared != _hash(unsigned) or payload["status"] != STATUS
            or payload["manifest_type"] != "ndx_dynamic_shadow_activation_v5"
            or _json(payload["boundaries"]) != _json(BOUNDARIES)
            or _json(payload["sources"]) != _json(_sources(root))
            or _json(payload["runner_contract"]) != _json(_contract(root))
            or payload["predecessor_static_manifest_sha256"] != file_sha256(root / PREDECESSOR)):
        raise ActivationV5Error("activation v5 identity, sources or boundaries changed")
    try:
        timestamp = datetime.fromisoformat(payload["generated_at_utc"])
        if timestamp.utcoffset() is None:
            raise ValueError("naive timestamp")
    except (TypeError, ValueError) as exc:
        raise ActivationV5Error("invalid activation timestamp") from exc
    verify_activation_v4_static_sources(root / PREDECESSOR, repository_root=root)
    _validate_proofs(payload["runtime_proofs"])
    prefix = path.parent / "calendar_event_prefix.json"
    if file_sha256(prefix) != payload["calendar_event_prefix_file_sha256"]:
        raise ActivationV5Error("frozen calendar prefix changed")
    return payload


def verify_activation_v5_manifest(path, *, repository_root):
    root = Path(repository_root).resolve()
    payload = verify_activation_v5_static_sources(path, repository_root=root)
    before = _evidence(root)
    prefix = json.loads((root / MANIFEST.parent / "calendar_event_prefix.json").read_text(encoding="utf-8"))
    if not isinstance(prefix, list) or not prefix or before["events"][:len(prefix)] != prefix:
        raise ActivationV5Error("reviewed calendar does not extend frozen prefix")
    if _json(_runtime_proofs(root)) != _json(payload["runtime_proofs"]):
        raise ActivationV5Error("runtime proof inventory changed")
    if (_json(_evidence(root)) != _json(before)
            or _json(verify_activation_v5_static_sources(path, repository_root=root)) != _json(payload)):
        raise ActivationV5Error("activation evidence changed during verification")
    return payload


def build_activation_v5_manifest(repository_root):
    root = Path(repository_root).resolve()
    path = root / MANIFEST
    if path.exists():
        return verify_activation_v5_manifest(path, repository_root=root)
    before = _evidence(root)
    proofs = _runtime_proofs(root)
    _validate_proofs(proofs)
    if _json(_evidence(root)) != _json(before):
        raise ActivationV5Error("activation evidence changed before publication")
    prefix_bytes = (json.dumps(before["events"], sort_keys=True, indent=2) + "\n").encode()
    payload = {
        "schema_version": 1, "manifest_type": "ndx_dynamic_shadow_activation_v5",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": STATUS,
        "predecessor_static_manifest_sha256": before["predecessor"],
        "runner_contract": before["contract"], "sources": before["sources"],
        "runtime_proofs": proofs, "boundaries": dict(BOUNDARIES),
        "calendar_event_prefix_file_sha256": hashlib.sha256(prefix_bytes).hexdigest(),
    }
    payload["manifest_sha256"] = _hash(payload)
    path.parent.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".activation-v5-bundle-", dir=path.parent.parent))
    for name, raw in (("calendar_event_prefix.json", prefix_bytes),
                      (path.name, (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode())):
        with (staging / name).open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    if path.parent.exists() or _json(_evidence(root)) != _json(before):
        raise ActivationV5Error("activation publication collision or evidence drift")
    os.rename(staging, path.parent)
    return verify_activation_v5_manifest(path, repository_root=root)
