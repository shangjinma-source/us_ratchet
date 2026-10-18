"""Candidate-v3 acceptance around the unchanged budgeted research controller.

The parent controller may write its original checkpoints and role seal. Those
outputs are not v4 accepted until this separate create-only receipt verifies.
This entry point neither registers a task nor creates trading orders.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ndx_dynamic_shadow_candidate_generator_v3 as candidate
from scripts.ndx_dynamic_shadow_fresh_search_v2 import execute as execute_budgeted
from scripts.ndx_dynamic_shadow_fresh_search_v3 import classify_completion
from backtest.ndx_dynamic_shadow_fresh_search import (
    canonical_sha256, verify_final_candidate_snapshot, verify_final_role_seal_record,
)

INPUT = Path("data/cache/research/ndx_dynamic_shadow_candidate_generator_v1")
SEARCH = Path("data/cache/research/ndx_dynamic_shadow_fresh_search_v1")
ACCEPTANCE = Path("data/cache/research/ndx_dynamic_shadow_fresh_search_v4_acceptance")
CODE_FILES = (
    "scripts/ndx_dynamic_shadow_fresh_search_v4.py",
    "scripts/ndx_dynamic_shadow_fresh_search_v3.py",
    "scripts/ndx_dynamic_shadow_fresh_search_v2.py",
    "scripts/ndx_dynamic_shadow_fresh_search.py",
    "backtest/ndx_dynamic_shadow_fresh_search.py",
    "backtest/ndx_dynamic_shadow_fresh_search_v2.py",
    "backtest/ndx_dynamic_shadow_search_budget.py",
    "config/ndx_dynamic_shadow_fresh_search_v1.yaml",
    "backtest/ndx_cardinality_discovery.py",
    "backtest/ndx_dynamic_candidate_policy.py",
    "config/ndx_dynamic_shadow_selector_registry_v1.yaml",
    "backtest/ndx_dynamic_shadow_selector_registry.py",
)
BOUNDARIES = dict(research_only=True, admission_allowed=False,
                  promotion_allowed=False, order_creation_allowed=False,
                  live_mutation_allowed=False, task_registration_performed=False)
FIELDS = {"schema_version", "receipt_type", "decision_date", "input_binding",
          "final_binding", "boundaries", "v4_verified"}
EXECUTOR_SOURCE_KEYS = {
    "contract_sha256": "config/ndx_dynamic_shadow_fresh_search_v1.yaml",
    "module_sha256": "backtest/ndx_dynamic_shadow_fresh_search.py",
    "script_sha256": "scripts/ndx_dynamic_shadow_fresh_search.py",
    "search_kernel_sha256": "backtest/ndx_cardinality_discovery.py",
    "selector_policy_sha256": "backtest/ndx_dynamic_candidate_policy.py",
    "selector_registry_sha256": "config/ndx_dynamic_shadow_selector_registry_v1.yaml",
    "selector_registry_validator_sha256": "backtest/ndx_dynamic_shadow_selector_registry.py",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def decision_date(value):
    require(isinstance(value, str), "decision date must be a string")
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value and parsed >= date(2026, 10, 1), "noncanonical decision date")
    return value


def bound_executor_hash(binding):
    """Match the frozen v2 executor identity using captured hashes, not rereads."""
    sources = binding["wrapper_sources"]
    return canonical_sha256({key: sources[path] for key, path in EXECUTOR_SOURCE_KEYS.items()})


def input_binding(snapshot_path):
    path = Path(snapshot_path).resolve()
    before = digest(path)
    snapshot = candidate.verify(path)
    original8 = snapshot.get("source_versions", {}).get("frozen_original8_manifest_sha256")
    require(isinstance(original8, str) and len(original8) == 64
            and all(character in "0123456789abcdef" for character in original8),
            "candidate input lacks valid frozen original8 source binding")
    decision = decision_date(snapshot["decision_date"])
    require(path == (ROOT / INPUT / decision / "manifest.json").resolve(), "noncanonical snapshot path")
    archive = snapshot["membership_evidence"]["candidate_v3_source_archive"]
    # The public candidate verifier validates every archived byte and all source semantics.
    binding = dict(snapshot_path=path.as_posix(), snapshot_sha256=before,
                   snapshot_fingerprint=snapshot["snapshot_fingerprint"],
                   candidate_source_versions=snapshot["source_versions"],
                   candidate_source_archive=archive,
                   wrapper_sources={name: digest(ROOT / name) for name in CODE_FILES})
    require(digest(path) == before, "snapshot changed while verifying")
    return snapshot, binding


def final_binding(snapshot, binding):
    decision = decision_date(snapshot["decision_date"])
    path = (ROOT / SEARCH / "final" / decision / "manifest.json").resolve()
    before = digest(path)
    final = verify_final_candidate_snapshot(path)
    record = verify_final_role_seal_record(
        path, ROOT / SEARCH / "role_seals.jsonl", expected_final_root=ROOT / SEARCH / "final",
    )
    require(final["decision_date"] == decision
            and final["snapshot_manifest_sha256"] == binding["snapshot_sha256"]
            and final["snapshot_fingerprint"] == binding["snapshot_fingerprint"],
            "final role seal belongs to a different candidate input")
    require(final.get("executor_sha256") == bound_executor_hash(binding),
            "final role seal executor differs from bound execution sources")
    require(final.get("original_8_sha256") == binding["candidate_source_versions"]["frozen_original8_manifest_sha256"],
            "final original8 differs from candidate input control binding")
    input_record = candidate.v1._verify_manifest_seal_record(
        Path(binding["snapshot_path"]), snapshot,
    )
    require(final["snapshot_seal_record_sha256"] == input_record["record_sha256"],
            "final role seal candidate ledger binding changed")
    require(digest(path) == before, "final snapshot changed while verifying")
    return dict(path=path.as_posix(), sha256=before, role_seal_record_sha256=record["record_sha256"])


def verify_acceptance(receipt_path):
    """Read-only verification; a legacy role seal alone never grants v4 acceptance."""
    path = Path(receipt_path).resolve()
    raw = path.read_bytes()
    receipt = json.loads(raw)
    require(isinstance(receipt, dict) and set(receipt) == FIELDS, "acceptance schema changed")
    decision = decision_date(receipt["decision_date"])
    require(path == (ROOT / ACCEPTANCE / decision / "receipt.json").resolve(), "noncanonical receipt path")
    boundaries = receipt["boundaries"]
    require(isinstance(boundaries, dict) and set(boundaries) == set(BOUNDARIES)
            and all(boundaries[key] is value for key, value in BOUNDARIES.items()),
            "acceptance boundary changed")
    require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
            and receipt["receipt_type"] == "CANDIDATE_V3_FRESH_SEARCH_V4_ACCEPTANCE"
            and receipt["boundaries"] == BOUNDARIES and receipt["v4_verified"] is True,
            "acceptance boundary changed")
    snapshot, binding = input_binding(ROOT / INPUT / decision / "manifest.json")
    require(binding == receipt["input_binding"], "acceptance input binding changed")
    require(final_binding(snapshot, binding) == receipt["final_binding"], "acceptance final binding changed")
    require(input_binding(ROOT / INPUT / decision / "manifest.json")[1] == binding,
            "input or code changed during acceptance verification")
    require(final_binding(snapshot, binding) == receipt["final_binding"],
            "final changed during acceptance verification")
    require(path.read_bytes() == raw, "acceptance changed during verification")
    return receipt


def publish(path, receipt):
    """Atomic create-only publication; existing evidence is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-v4-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            require(verify_acceptance(path) == receipt, "immutable acceptance collision")
    finally:
        temporary.unlink(missing_ok=True)


def execute(snapshot_path):
    path = Path(snapshot_path).resolve()
    snapshot, before = input_binding(path)
    receipt_path = ROOT / ACCEPTANCE / decision_date(snapshot["decision_date"]) / "receipt.json"
    if receipt_path.exists():
        receipt = verify_acceptance(receipt_path)
        return dict(v4_verified=True, completed=True, receipt_path=receipt_path.as_posix(), receipt=receipt)
    result = execute_budgeted(path)
    _, after = input_binding(path)
    require(before == after, "candidate input/archive or code changed during controller execution")
    completion = classify_completion(result)
    require(result.get("snapshot_manifest_sha256") == before["snapshot_sha256"], "controller input binding changed")
    require(result.get("v1_executor_sha256") == bound_executor_hash(before),
            "controller executor differs from bound execution sources")
    if not completion["completed"]:
        return dict(v4_verified=False, completed=False, completion=completion, controller=result)
    receipt = dict(schema_version=1, receipt_type="CANDIDATE_V3_FRESH_SEARCH_V4_ACCEPTANCE",
                   decision_date=snapshot["decision_date"], input_binding=before,
                   final_binding=final_binding(snapshot, before), boundaries=BOUNDARIES, v4_verified=True)
    require(input_binding(path)[1] == before, "candidate changed before acceptance publication")
    require(final_binding(snapshot, before) == receipt["final_binding"],
            "final changed before acceptance publication")
    publish(receipt_path, receipt)
    verified = verify_acceptance(receipt_path)
    return dict(v4_verified=True, completed=True, receipt_path=receipt_path.as_posix(), receipt=verified)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--verify-acceptance", type=Path)
    parser.add_argument("--snapshot-manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.execute:
            require(args.snapshot_manifest is not None, "--snapshot-manifest is required")
            result = execute(args.snapshot_manifest)
        else:
            result = dict(v4_verified=True, completed=True, receipt=verify_acceptance(args.verify_acceptance))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["completed"] else result["completion"]["exit_code"]
    except Exception as exc:
        print(json.dumps(dict(v4_verified=False, completed=False, error=f"{type(exc).__name__}: {exc}")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
