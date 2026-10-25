"""Read-only admission for preparing a NEW prospective paper registration.

This does not clear a failed attempt, authorize activation, or dispatch trading.
"""
import argparse
from datetime import datetime, time, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import register_quantity_v2_paper_protocol as registrar
from scripts import run_registered_quantity_v2_paper_simulation as runtime


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def inspect_failed_state(root, descriptor, validated, new_directory, start_session, now):
    root = Path(root).resolve()
    old = registrar.safe_path(root, descriptor["registration_directory"])
    target = registrar.safe_path(root, new_directory)
    need(not target.exists() and not target.is_relative_to(old)
         and not old.is_relative_to(target), "NEW_REGISTRATION_PATH_REQUIRED")
    raw_database = Path(validated["request"]["identity"]["database_path"])
    if not raw_database.is_absolute():
        raw_database = root / raw_database
    for suffix in ("", "-wal", "-shm", "-journal"):
        original = Path(str(raw_database) + suffix)
        for component in (original, *original.parents):
            need(not component.is_symlink()
                 and not getattr(component, "is_junction", lambda: False)(),
                 "DATABASE_LINK_REQUIRES_REVIEW")
    database = Path(validated["database_path"])
    need(raw_database.resolve() == database.resolve(), "DATABASE_PATH_BINDING_MISMATCH")
    need(database.resolve().is_relative_to(root), "DATABASE_OUTSIDE_ROOT")
    need(not any(Path(str(database) + suffix).exists()
                 for suffix in ("", "-wal", "-shm", "-journal")), "DATABASE_OR_SIDECAR_EXISTS")
    logs = registrar.safe_path(root, descriptor["log_directory"])
    need(not (logs / "running.lock").exists()
         and not registrar.safe_path(root, registrar.LOCK).exists(), "LOCK_REQUIRES_REVIEW")
    directory = old / "runtime"
    required = ("bootstrap_reconciliation_required.json",
                "execution_reconciliation_required.json",
                "bootstrap-attempt/failed.json", "bootstrap-attempt/started.json")
    evidence = {}
    for name in required:
        path = registrar.safe_path(root, (directory / name).relative_to(root).as_posix())
        raw = path.read_bytes()
        value = json.loads(raw)
        need(value.get("request_sha256") == descriptor["request_sha256"],
             "FAILURE_REQUEST_MISMATCH")
        evidence[str(path.relative_to(root))] = sha256(raw).hexdigest()
    # No successful runtime result may be silently abandoned, even without a DB.
    for path in directory.rglob("*"):
        need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
             "RUNTIME_LINK_REQUIRES_REVIEW")
        need(path.name not in ("complete.json", "result.json", "start.json",
                               "start_complete.json"), "SUCCESS_RECEIPT_REQUIRES_REVIEW")
    request = validated["request"]
    need(start_session > request["evaluation"]["start_session"], "NEW_START_MUST_ADVANCE")
    sessions = {row["date"]: row for row in validated["calendar"]["sessions"]}
    need(start_session in sessions, "START_NOT_IN_FIXED_CALENDAR")
    first = datetime.combine(datetime.fromisoformat(start_session).date(),
                             time(10), ZoneInfo("America/New_York"))
    row = sessions[start_session]
    need(datetime.fromisoformat(row["open_at"]) <= first < datetime.fromisoformat(row["close_at"]),
         "FIRST_DECISION_OUTSIDE_SESSION")
    need(now < first, "PROSPECTIVE_START_ALREADY_PASSED")
    return dict(status="NEW_REGISTRATION_PREPARATION_ONLY", first_decision_at=first.isoformat(),
                proposed_registration_directory=new_directory, failure_evidence=evidence,
                old_evidence_preserved=True, account_writes=False, task_changes=False,
                dispatch_authorized=False,
                remaining_requirements=["new request and authorization with prospective evaluation",
                                        "new isolated audit/output paths",
                                        "validate and register new bundle before first decision",
                                        "independent task cutover review"])


def run(*, descriptor_path, expected_descriptor_sha256, new_directory, start_session, clock=None):
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    original = Path(descriptor_path).absolute()
    for component in (original, *original.parents):
        need(not component.is_symlink()
             and not getattr(component, "is_junction", lambda: False)(),
             "DESCRIPTOR_LINK_NOT_ALLOWED")
    path = original.resolve()
    raw = path.read_bytes()
    need(sha256(raw).hexdigest() == expected_descriptor_sha256, "DESCRIPTOR_HASH_MISMATCH")
    descriptor = json.loads(raw)
    need(descriptor.get("schema") == "REGISTERED_PAPER_AUTOMATION_V1", "DESCRIPTOR_SCHEMA")
    root = Path(descriptor["root"]).resolve()
    need(path.is_relative_to(root), "DESCRIPTOR_OUTSIDE_ROOT")
    for name, expected in descriptor["source_hashes"].items():
        source = registrar.safe_path(root, name)
        need(sha256(source.read_bytes()).hexdigest() == expected, "ORIGINAL_SOURCE_CHANGED")
    validated = runtime.load_bundle(root=root, registration_directory=descriptor["registration_directory"],
                                    expected_request_sha256=descriptor["request_sha256"], now=now)
    return inspect_failed_state(root, descriptor, validated, new_directory, start_session, now)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor-path", required=True)
    parser.add_argument("--expected-descriptor-sha256", required=True)
    parser.add_argument("--new-directory", required=True)
    parser.add_argument("--start-session", required=True)
    try:
        result = run(**vars(parser.parse_args()))
    except (ValueError, OSError, KeyError) as error:
        result = dict(status="BLOCKED", reason=str(error) if isinstance(error, ValueError)
                      else type(error).__name__)
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
