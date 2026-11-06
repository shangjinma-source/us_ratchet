"""Explicit capture + conditional training only; default dry-run, never activates."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from scripts.monthly_experimental_domain_capture import run as capture_domain
from scripts.build_monthly_successor_plan import prepare as validate_plan, completed_previous
from scripts.current_research_close_capture import default_fetch
from scripts.research.prepare_roa_fixed_domain_training import prepare, write_outputs, read_reference


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def run(*, root, request, capture=False, fetch=default_fetch, clock=lambda: datetime.now(timezone.utc)):
    root = Path(root).resolve()
    if set(request) != {"plan", "training_calendar", "output_directory"}:
        raise ValueError("RUNNER_REQUEST_FIELDS")
    pins = {}
    read_reference(root, request["plan"], pins)
    read_reference(root, request["training_calendar"], pins)
    relative = Path(request["output_directory"])
    output = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or output == root or not output.is_relative_to(root):
        raise ValueError("RUNNER_OUTPUT_INVALID")
    plan, preflight = validate_plan(request["plan"]["path"], request["plan"]["sha256"], root=root, clock=clock)
    completion = output / "completion.json"
    seal = output / "runner_receipt.json"
    if output.exists():
        if not seal.is_file():
            raise ValueError("INCOMPLETE_OUTPUT_NOT_REUSABLE")
        saved = json.loads(seal.read_bytes())
        if saved["request"] != request:
            raise ValueError("COMPLETION_REQUEST_MISMATCH")
        for name, expected in saved["output_hashes"].items():
            read_reference(root, dict(path=name, sha256=expected), {})
        adapter_receipt = json.loads((output / "receipt.json").read_bytes())
        for name, expected in adapter_receipt["source_hashes"].items():
            source = (root / name).resolve()
            if Path(name).is_absolute() or ".." in Path(name).parts or not source.is_relative_to(root):
                raise ValueError("REUSED_SOURCE_PATH_INVALID")
            if not source.is_file() or digest(source) != expected:
                raise ValueError("REUSED_ADAPTER_SOURCE_CHANGED:" + name)
        completed_previous(root, (output/"manifest.json").relative_to(root).as_posix(), saved["output_hashes"][(output/"manifest.json").relative_to(root).as_posix()],
            completion.relative_to(root).as_posix(), saved["output_hashes"][completion.relative_to(root).as_posix()], clock)
        return dict(status="VERIFIED_COMPLETION_REUSED", http_calls=0, account_writes=False, activated=False)
    if not preflight["ready_after_close"]:
        return dict(status="WAIT_COMPLETED_MONTH_END", http_calls=0, account_writes=False, activated=False)
    if not capture:
        return dict(status="DRY_RUN_READY_NO_HTTP", http_calls=0, account_writes=False, activated=False)
    captured = capture_domain(request["plan"]["path"], request["plan"]["sha256"], root=root,
                             capture=True, fetch=fetch, clock=clock, plan_validator=validate_plan)
    if captured["status"] != "EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED":
        raise ValueError("CAPTURE_INCOMPLETE_NO_TRAINING_COMPLETION")
    index = plan["output_directory"] + "/completion_index.json"
    ref = lambda name, expected=None: dict(path=name, sha256=expected or digest(root/name))
    adapter_request = dict(prior_manifest=ref(plan["previous_manifest_path"], plan["previous_manifest_sha256"]),
        fixed_domain=ref(plan["domain_path"], plan["domain_source_hashes"][plan["domain_path"]]),
        capture_plan=request["plan"], capture_index=ref(index),
        session_calendar=ref(plan["calendar_path"], plan["calendar_source_hashes"][plan["calendar_path"]]),
        training_calendar=request["training_calendar"])
    manifest, report = prepare(root, adapter_request, clock())
    write_outputs(output, manifest, report)
    hashes = {(output/name).relative_to(root).as_posix(): digest(output/name) for name in ("manifest.json", "receipt.json", "completion.json")}
    completed_previous(root, (output/"manifest.json").relative_to(root).as_posix(), digest(output/"manifest.json"),
                       completion.relative_to(root).as_posix(), digest(completion), clock)
    result = dict(status="PREPARED_VERIFIED_NOT_ACTIVATED", request=request, output_hashes=hashes,
                  http_calls=captured["http_calls"], account_writes=False, activated=False)
    with seal.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    result = run(root=Path(__file__).resolve().parents[2], request=json.loads(Path(args.request).read_bytes()), capture=args.capture)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
