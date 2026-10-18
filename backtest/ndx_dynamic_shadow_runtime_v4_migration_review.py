"""Deterministic review draft. Never an authorization, installer, or live gate."""
from pathlib import Path
import hashlib
import json

from backtest.ndx_dynamic_shadow_activation_v5 import SOURCES as RUNTIME_SOURCES, MANIFEST

REVIEW_PATH = Path("data/cache/research/ndx_dynamic_shadow_task_migration_v4/review_draft.json")
SOURCES = tuple(sorted(set(RUNTIME_SOURCES) | {
    "backtest/ndx_observed_session_calendar.py",
    "backtest/ndx_dynamic_whole_lot_path.py",
    "backtest/ndx_dynamic_shadow_runtime_v4_migration.py",
    "backtest/ndx_dynamic_shadow_runtime_v4_migration_review.py",
    "scripts/ndx_dynamic_shadow_runtime_v4_migration.py",
    "scripts/ndx_dynamic_shadow_runtime_v4_migration_review.py",
    "scripts/ndx_dynamic_shadow_runtime_v4_smoke.py",
    "tests/test_ndx_dynamic_shadow_runtime_v4_migration.py",
    "tests/test_ndx_dynamic_shadow_runtime_v4_migration_review.py",
    "tests/test_ndx_dynamic_shadow_runtime_v4_smoke.py",
    "tests/test_ndx_dynamic_shadow_runtime_v4_smoke_e2e.py",
    "tests/test_migrate_ndx_dynamic_shadow_selection_task_v4_e2e.py",
    "tests/fixture_runtime_v4_installer.ps1",
}))
REQUIRED_COMPONENTS = (
    "scripts/migrate_ndx_dynamic_shadow_selection_task_v4.ps1",
    "scripts/ndx_dynamic_shadow_runtime_v4_task_evidence.py",
    "tests/test_migrate_ndx_dynamic_shadow_selection_task_v4.py",
    "tests/test_ndx_dynamic_shadow_runtime_v4_task_evidence.py",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique_fields(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate review field")
        value[key] = item
    return value


def _capture(root):
    bound = {}
    missing = []
    for relative in sorted(set(SOURCES) | set(REQUIRED_COMPONENTS)):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("review source escapes repository")
        if not path.is_file():
            if relative in SOURCES:
                raise ValueError("required existing review source missing: " + relative)
            missing.append(relative)
        else:
            bound[relative] = {"path": path.as_posix(), "sha256": _sha(path.read_bytes())}
    activation = (root / MANIFEST).resolve()
    if not activation.is_relative_to(root):
        raise ValueError("activation path escapes repository")
    return {"sources": bound, "missing_required_components": missing,
            "activation_snapshot": {"path": activation.as_posix(),
                "sha256": _sha(activation.read_bytes()) if activation.is_file() else None,
                "full_verification_performed": False}}


def build_review_draft(repository_root):
    root = Path(repository_root).resolve()
    captured = _capture(root)
    payload = {"schema_version": 1,
               "manifest_type": "ndx_dynamic_shadow_runtime_v4_migration_review_draft",
               "status": "REVIEW_DRAFT_NOT_AUTHORIZATION",
               **captured,
               "remaining_execution_requirements": [
                   "INDEPENDENT_USER_APPROVAL_BOUND_TO_EXACT_REVIEW_HASH",
                   "FULL_ACTIVATION_V5_AND_MIGRATION_TESTS_REPLAYED_AT_CUTOVER",
                   "DISABLED_REGISTRATION_AND_EXACT_TASK_CONTRACT_VERIFIED",
                   "ACTUAL_TASK_RUN_EVIDENCE_SEPARATE_FROM_ARTIFACT_SMOKE",
                   "FAILURE_ROLLBACK_AND_INTERRUPTED_RECOVERY_VERIFIED",
               ],
               "boundaries": {"user_approval_recorded": False, "task_registration_allowed": False,
                   "cutover_allowed": False, "task_mutation_performed": False,
                   "live_mutation_allowed": False, "promotion_allowed": False,
                   "tests_executed_by_this_builder": False,
                   "component_presence_proves_correctness": False,
                   "old_v2_or_v3_approval_reused": False}}
    if _canonical(_capture(root)) != _canonical(captured):
        raise ValueError("review source or component inventory changed during capture")
    payload["review_sha256"] = _sha(_canonical(payload).encode())
    return payload


def verify_review_draft(path, *, repository_root):
    root, path = Path(repository_root).resolve(), Path(path).resolve()
    if path != (root / REVIEW_PATH).resolve():
        raise ValueError("review draft path is not canonical")
    raw = path.read_bytes()
    # Reconstruct every field instead of trusting caller-supplied approval flags.
    value = json.loads(raw, object_pairs_hook=_unique_fields)
    if _canonical(value) != _canonical(build_review_draft(root)):
        raise ValueError("review draft differs from current sources or boundaries")
    if path.read_bytes() != raw:
        raise ValueError("review draft changed during verification")
    return value
