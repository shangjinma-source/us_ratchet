"""Read-only, current-run evidence for an actual Scheduled Task smoke.

This does not start a task or infer task execution from a file. The installer
must independently verify LastRunTime/LastTaskResult. Post verification is a
cutover-time check: a later legitimate run requires a new health observation,
not rewriting the original migration receipt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_daily_v2 import verify_daily_run_manifest

LATEST = Path("data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("smoke timestamps must have an explicit timezone")
    return result.astimezone(timezone.utc)


def snapshot(root: Path) -> dict:
    path = (root / LATEST).resolve()
    return {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "latest_run_path": path.as_posix(),
        "latest_run_sha256": _hash(path.read_bytes()) if path.is_file() else None,
    }


def verify(root: Path, *, before: dict | None = None, expected: dict | None = None) -> dict:
    if (before is None) == (expected is None):
        raise ValueError("exactly one before snapshot or expected proof is required")
    path = (root / LATEST).resolve()
    raw = path.read_bytes()
    digest = _hash(raw)
    parsed = json.loads(raw)
    generated = _time(parsed["generated_at"])
    if generated > datetime.now(timezone.utc):
        raise ValueError("daily run timestamp is in the future")
    if before is not None:
        if (set(before) != {"schema_version", "captured_at_utc", "latest_run_path", "latest_run_sha256"}
                or before["schema_version"] != 1
                or before["latest_run_path"] != path.as_posix()
                or before["latest_run_sha256"] == digest
                or generated < _time(before["captured_at_utc"])):
            raise ValueError("no fresh canonical daily run from this smoke")
    verified = verify_daily_run_manifest(path, repository_root=root)
    if path.read_bytes() != raw or verified != parsed:
        raise ValueError("daily run changed during smoke verification")
    proof = {
        "schema_version": 1,
        "latest_run_path": path.as_posix(),
        "latest_run_sha256": digest,
        "run_generated_at": parsed["generated_at"],
        "run_manifest_sha256": parsed["run_manifest_sha256"],
        "status": parsed["status"],
        "latest_observed_session": parsed["latest_observed_session"],
        "independent_lane_count": parsed["independent_lane_count"],
        "full_daily_v2_verifier_replayed": True,
        "task_execution_verified_by_this_tool": False,
        "promotion_allowed": False,
    }
    if expected is not None and expected != proof:
        raise ValueError("cutover run was changed or superseded; original proof is not current health")
    return proof


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", action="store_true")
    mode.add_argument("--verify", action="store_true")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--before-path", type=Path)
    source.add_argument("--expected-path", type=Path)
    args = parser.parse_args()
    try:
        if args.snapshot:
            result = snapshot(ROOT)
        elif args.before_path:
            record = json.loads(args.before_path.read_text(encoding="utf-8-sig"))
            result = verify(ROOT, before=record["smoke_before"])
        elif args.expected_path:
            record = json.loads(args.expected_path.read_text(encoding="utf-8-sig"))
            result = verify(ROOT, expected=record["smoke"]["artifact_verification"])
        else:
            raise ValueError("verify requires --before-path or --expected-path")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"runtime-v3 smoke evidence failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
