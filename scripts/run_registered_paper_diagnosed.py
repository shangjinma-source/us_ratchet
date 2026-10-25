"""Prospective launcher with bounded safe diagnostics; original runtime unchanged."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import sys
from pathlib import Path
from uuid import uuid4

from scripts import run_registered_paper_automation as original
from scripts import register_quantity_v2_paper_protocol as registrar
from scripts.paper_failure_diagnostics import observe

SUCCESS = {"PREFLIGHT_ONLY", "COMPLETE", "REGISTERED_BOOTSTRAP_COMPLETE", "SKIPPED",
           "SKIPPED_NO_DISPATCH", "WAITING_ACCOUNT", "WAITING_FIRST_SESSION",
           "WAITING_SESSION_CLOSE", "EVALUATION_ENDED_NO_MONTHLY_WORK",
           "MONTHLY_COMPLETE_NEXT_PLAN_READY"}


def run(*, descriptor_path, expected_descriptor_sha256, mode, execute=False):
    path = Path(descriptor_path)
    for component in (path.absolute(), *path.absolute().parents):
        registrar.require(not component.is_symlink()
                          and not getattr(component, "is_junction", lambda: False)(),
                          "DIAGNOSTIC_DESCRIPTOR_LINK")
    raw = path.read_bytes()
    registrar.require(sha256(raw).hexdigest() == expected_descriptor_sha256,
                      "AUTOMATION_DESCRIPTOR_CHANGED")
    descriptor = json.loads(raw)
    root = Path(descriptor["root"]).resolve()
    for name in ("scripts/run_registered_paper_diagnosed.py", "scripts/paper_failure_diagnostics.py"):
        registrar.require(descriptor["source_hashes"].get(name)
                          == sha256((root / name).read_bytes()).hexdigest(),
                          "DIAGNOSTIC_EXECUTABLE_PIN_REQUIRED")
    directory = registrar.safe_path(root, descriptor["log_directory"] + "-diagnostics")
    snapshots = []
    try:
        result = observe(lambda: original.run(descriptor_path=descriptor_path,
                         expected_descriptor_sha256=expected_descriptor_sha256,
                         mode=mode, execute=execute), root=root, sink=snapshots.append)
    except Exception as error:
        try:
            message = str(error)
        except Exception:
            message = ""
        reason = message if isinstance(error, ValueError) and message.replace("_", "").isalnum() else "AUTOMATION_BLOCKED"
        result = dict(status="BLOCKED", reason=reason)
    code = 0 if result.get("status") in SUCCESS else 2
    diagnostic = dict(schema="PAPER_DIAGNOSED_LAUNCH_V1",
                      descriptor_sha256=expected_descriptor_sha256, mode=mode,
                      recorded_at=datetime.now(timezone.utc).isoformat(),
                      exit_code=code, result=result, snapshots=snapshots)
    # Diagnostics never enter the original attempt directory or reconciliation state.
    if execute:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            registrar.save(directory / (uuid4().hex + ".json"), diagnostic)
        except Exception:
            diagnostic["persistence_failed"] = True
            try:
                sys.stderr.write("PAPER_DIAGNOSTIC_PERSISTENCE_FAILED\n")
            except Exception:
                pass
    return result, code, diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor-path", required=True)
    parser.add_argument("--expected-descriptor-sha256", required=True)
    parser.add_argument("--mode", choices=["daily", "monthly"], required=True)
    parser.add_argument("--execute", action="store_true")
    result, code, _ = run(**vars(parser.parse_args()))
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
