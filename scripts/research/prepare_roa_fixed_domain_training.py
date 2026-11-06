"""Offline fixed-domain capture adapter; no collection, selection or activation."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


def read_reference(root, reference, pins):
    if set(reference) != {"path", "sha256"}:
        raise ValueError("REFERENCE_FIELDS")
    name = reference["path"]
    path = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts or not path.resolve().is_relative_to(root):
        raise ValueError("SOURCE_PATH_INVALID")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("SOURCE_CHANGED:" + name)
    pins[name] = reference["sha256"]
    return json.loads(raw)


def validate_bindings(prior, domain, plan, index, training, request):
    for key, ref in (("previous_manifest_path", "prior_manifest"), ("domain_path", "fixed_domain"),
                     ("calendar_path", "session_calendar")):
        if plan[key] != request[ref]["path"]:
            raise ValueError("PLAN_REFERENCE_MISMATCH")
    if plan["previous_manifest_sha256"] != request["prior_manifest"]["sha256"]:
        raise ValueError("PRIOR_REFERENCE_MISMATCH")
    if plan["domain_source_hashes"].get(plan["domain_path"]) != request["fixed_domain"]["sha256"] or plan["calendar_source_hashes"].get(plan["calendar_path"]) != request["session_calendar"]["sha256"]:
        raise ValueError("PLAN_SOURCE_BINDING_MISMATCH")
    day = plan["session"]
    if day <= prior["decision_date"] or index["session"] != day or index["plan_sha256"] != request["capture_plan"]["sha256"]:
        raise ValueError("CAPTURE_DATE_OR_PLAN_MISMATCH")
    candidates = prior["candidates"]
    expected = {(r["ticker"], r["security_id"], r["issuer_id"]) for r in candidates}
    actual = {(r["ticker"], r["security_id"], r["issuer_id"]) for r in domain["securities"]}
    if len(expected) != len(candidates) or expected != actual or len(actual) != len(domain["securities"]):
        raise ValueError("FIXED_DOMAIN_IDENTITY_MISMATCH")
    pairs = {(t, sid) for t, sid, issuer in expected}
    for rows in (plan["securities"], index["entries"]):
        if len(rows) != len(pairs) or {(r["ticker"], r["security_id"]) for r in rows} != pairs:
            raise ValueError("CAPTURE_DOMAIN_OR_SID_MISMATCH")
    dates = [r["date"] for r in training["sessions"]]
    if dates != sorted(set(dates)) or day not in dates:
        raise ValueError("TRAINING_CALENDAR_INVALID")
    following = next((d for d in dates if d > day), None)
    if following is None or following[:7] == day[:7]:
        raise ValueError("NOT_COMPLETE_MONTH_END")
    window = [d for d in dates if d <= day][-253:]
    if len(window) != 253:
        raise ValueError("TRAINING_CALENDAR_TOO_SHORT")
    return window


def prepare(root, request, now):
    from scripts.prepare_monthly_captured_training import build
    from scripts.build_monthly_successor_plan import prepare as validate_plan
    root = Path(root).resolve()
    if now.tzinfo is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    required = {"prior_manifest", "fixed_domain", "capture_plan", "capture_index", "session_calendar", "training_calendar"}
    if set(request) != required:
        raise ValueError("REQUEST_FIELDS")
    pins = {}
    docs = {k: read_reference(root, v, pins) for k, v in request.items()}
    training = docs["training_calendar"]
    if training["schema"] not in ("VERIFIED_SCHEDULE_DATES_V1", "FIXED_EXCHANGE_SESSIONS_V1"):
        raise ValueError("TRAINING_CALENDAR_SCHEMA")
    for reference in training.get("source_references", []):
        # Evidence can be raw HTML/PDF, not only JSON.
        name = reference["path"]
        target = (root / name).resolve()
        if not target.is_relative_to(root) or sha256(target.read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("CALENDAR_SOURCE_CHANGED")
        pins[name] = reference["sha256"]
    window = validate_bindings(docs["prior_manifest"], docs["fixed_domain"], docs["capture_plan"], docs["capture_index"], training, request)
    manifest, compiled, report = build(root=root,
        previous_manifest_path=request["prior_manifest"]["path"], previous_manifest_sha256=request["prior_manifest"]["sha256"],
        capture_index_path=request["capture_index"]["path"], capture_index_sha256=request["capture_index"]["sha256"],
        plan_path=request["capture_plan"]["path"], plan_sha256=request["capture_plan"]["sha256"],
        clock=lambda: now, plan_validator=validate_plan)
    if manifest["training_dates"] != window:
        raise ValueError("EXACT_TRAINING_CALENDAR_MISMATCH")
    if compiled["status"] != "READY_CONDITIONAL":
        raise ValueError("TRAINING_NOT_READY_CONDITIONAL")
    # Preserve original output bytes/claims; extra adapter evidence belongs in receipt.
    return manifest, dict(status="PREPARED_CONDITIONAL_NOT_ACTIVATED", decision_date=manifest["decision_date"],
        source_hashes=pins, preparation=report, network_calls=0, account_writes=False,
        identity_upgraded=False, corporate_actions_upgraded=False, pit_upgraded=False,
        checked_at=now.isoformat(), binding_inputs=dict(
            previous_manifest_path=request["prior_manifest"]["path"], previous_manifest_sha256=request["prior_manifest"]["sha256"],
            capture_index_path=request["capture_index"]["path"], capture_index_sha256=request["capture_index"]["sha256"],
            plan_path=request["capture_plan"]["path"], plan_sha256=request["capture_plan"]["sha256"]))


def write_outputs(output, manifest, report):
    output = Path(output)
    if report.get("status") != "PREPARED_CONDITIONAL_NOT_ACTIVATED" or "binding_inputs" not in report:
        raise ValueError("VERIFIED_PREPARATION_REQUIRED")
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, value in (("manifest", manifest), ("receipt", report)):
        with (output / (name + ".json")).open("xb") as stream:
            raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            stream.write(raw)
        hashes[str((output / (name + ".json")).resolve())] = sha256(raw).hexdigest()
    completion = dict(result={"status": "READY_CONDITIONAL"}, output_hashes=hashes,
                      at=datetime.now(timezone.utc).isoformat(), binding={"inputs": report["binding_inputs"]},
                      limitations=["Completion of this offline replay now, not historical capture availability or activation"] )
    with (output / "completion.json").open("xb") as stream:
        stream.write(json.dumps(completion, sort_keys=True, separators=(",", ":")).encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest, receipt = prepare(Path(__file__).resolve().parents[2], json.loads(Path(args.request).read_bytes()), datetime.now(timezone.utc))
    write_outputs(args.output, manifest, receipt)
    print(json.dumps(dict(output=args.output, status=receipt["status"], candidates=len(manifest["candidates"]))))


if __name__ == "__main__":
    main()
