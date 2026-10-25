"""Pinned, create-only daily source pipeline. Never changes accounts or releases."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import capture_session, pinned, reject_links, require, stamp
from data.strategy_daily_continuity_normalizer import normalize_saved_capture

RUNNER_CODE_PATHS = {
    "data/strategy_daily_source_runner.py", "scripts/run_daily_source_pipeline.py",
    "data/strategy_account_runtime.py", "core/strategy_account_store.py",
    "core/strategy_monthly_target_store.py",
}


def run_daily_sources(*, root, configuration_bytes, configuration_sha256, execute=False,
                      account_reader=None, target_reader=None, fetch_daily=None,
                      fetch_official=None, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    reject_links(root)
    root = Path(root).resolve()
    require(sha256(configuration_bytes).hexdigest() == configuration_sha256, "PIPELINE_CONFIG_CHANGED")
    config = json.loads(configuration_bytes)
    require(config["schema"] == "SERVER_DAILY_SOURCE_PIPELINE_V1", "PIPELINE_SCHEMA")
    require(RUNNER_CODE_PATHS <= {r["path"] for r in config["source_pins"]}, "PIPELINE_SOURCE_PINS")
    for reference in config["source_pins"]:
        raw = pinned(root, reference)
        if reference["path"] in RUNNER_CODE_PATHS:
            require(raw == (Path(__file__).resolve().parents[1]/reference["path"]).read_bytes(),
                    "EXECUTING_PIPELINE_CHANGED")
    capture_raw = pinned(root, config["capture_configuration"])
    capture_config = json.loads(capture_raw)
    current = stamp(clock())
    today = current.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    if today < config["first_execution_date"]:
        return dict(status="WAIT_FIRST_EXECUTION_DATE", session=today, http_calls=0)
    # This also checks identity/calendar/source pins without creating files.
    readiness = capture_session(root=root, configuration_bytes=capture_raw,
        configuration_sha256=config["capture_configuration"]["sha256"], clock=clock, execute=False)
    if readiness["status"] not in ("DRY_RUN_NO_HTTP_NO_FILES", "EXISTING_CAPTURE_REQUIRES_RECEIPT_REVIEW"):
        return readiness
    run_directory = root/config["runs_root"]/today
    reject_links(run_directory)
    run_directory = run_directory.resolve()
    require(run_directory.is_relative_to(root), "RUN_DIRECTORY_OUTSIDE_ROOT")
    terminal_path = run_directory/"terminal.json"
    if run_directory.exists():
        reject_links(terminal_path)
        if not terminal_path.is_file():
            return dict(status="NEEDS_RECOVERY", reason="INCOMPLETE_DAILY_PIPELINE_RUN", http_calls=0)
        terminal = json.loads(terminal_path.read_bytes())
        if terminal.get("status") != "DAILY_CONDITIONAL_PACKET_SAVED":
            return dict(status="NEEDS_RECOVERY", reason=terminal.get("reason", terminal.get("status")), http_calls=0)
        require(terminal["configuration_sha256"] == configuration_sha256
                and terminal["session"] == today, "SAVED_RUN_BINDING_CHANGED")
        require(terminal["receipt_reference"]["path"] == (run_directory/"receipt.json").relative_to(root).as_posix()
                and terminal["manifest_reference"]["path"] == (run_directory/"source-paths.json").relative_to(root).as_posix(),
                "SAVED_RUN_PATH_CHANGED")
        receipt_raw = pinned(root, terminal["receipt_reference"])
        manifest = json.loads(pinned(root, terminal["manifest_reference"]))
        receipt = json.loads(receipt_raw)
        require(set(manifest) == set(receipt["source_sha256"]) and 0 < len(manifest) <= 2000,
                "SAVED_PACKET_DOMAIN_CHANGED")
        require(receipt["execution_session"]["date"] == today
                and receipt.get("release_sha256") == json.loads(pinned(root, config["parent_reference"])).get("release_sha256"),
                "SAVED_PACKET_SESSION_OR_POLICY_CHANGED")
        total = 0
        for name, reference in manifest.items():
            require(reference["sha256"] == receipt["source_sha256"][name], "SAVED_PACKET_PIN_CHANGED")
            require(reference["path"] == (run_directory/"files"/(reference["sha256"]+".bin")).relative_to(root).as_posix(),
                    "SAVED_PACKET_PATH_CHANGED")
            total += len(pinned(root, reference))
            require(total <= 32*1024*1024, "SAVED_PACKET_BUDGET")
        return dict(status="EXISTING_DAILY_PACKET_VERIFIED", session=today,
                    receipt_reference=terminal["receipt_reference"], http_calls=0, policy_approved=False)
    if not execute:
        return dict(status="DRY_RUN_NO_HTTP_NO_FILES", session=today, http_calls=0,
                    run_directory=str(run_directory), capture_readiness=readiness)
    if account_reader is None or target_reader is None:
        from data.strategy_account_runtime import ScopedAccountStore
        from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
        account_path, target_path = root/config["account_database"], root/config["target_database"]
        for path in (account_path, target_path):
            reject_links(path)
            require(path.resolve().is_relative_to(root) and path.is_file(), "DATABASE_PATH_REQUIRED")
        account_reader = ScopedAccountStore(account_path).read
        target_reader = StrategyMonthlyTargetStore(target_path).current
    state, target = account_reader(), target_reader()
    if not state or not target:
        return dict(status="WAIT_ACCOUNT_OR_MONTHLY_TARGET", http_calls=0)
    require(state["account_id"] == config["account_id"] == target["payload"]["account_id"],
            "PIPELINE_ACCOUNT_BINDING")
    if target["payload"]["target_month"] != today[:7]:
        return dict(status="WAIT_MONTHLY_TARGET", http_calls=0)
    run_directory.mkdir(parents=True, exist_ok=False)
    def save(name, raw):
        path = run_directory/name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw if isinstance(raw, bytes) else canonical(raw))
        return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
    save("started.json", dict(session=today, configuration_sha256=configuration_sha256,
        started_at=current.isoformat(), account_revision=state["revision"], target_id=target["target_id"],
        account_mutated=False, policy_approved=False))
    save("pipeline-configuration.json", configuration_bytes)
    captured = None
    try:
        captured = capture_session(root=root, configuration_bytes=capture_raw,
            configuration_sha256=config["capture_configuration"]["sha256"], execute=True,
            fetch_daily=fetch_daily, fetch_official=fetch_official, clock=clock)
        require(captured["status"] in ("CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED",
                                      "EXISTING_CAPTURE_REQUIRES_RECEIPT_REVIEW"), "CAPTURE_NOT_READY")
        result = normalize_saved_capture(root=root,
            capture_directory=str(Path(capture_config["output_root"])/today),
            expected_configuration_sha256=config["capture_configuration"]["sha256"],
            parent_reference=config["parent_reference"], state=state, target=target, clock=clock)
        require(result["status"] == "CONDITIONAL_DAILY_EVIDENCE_READY_POLICY_UNCHANGED",
                result.get("reason", result["status"]))
        require(account_reader() == state and target_reader() == target, "PIPELINE_SNAPSHOT_CHANGED")
        session_close = stamp(result["receipt"]["execution_session"]["close"])
        def publication_check():
            require(account_reader() == state and target_reader() == target, "PIPELINE_SNAPSHOT_CHANGED")
            checked = stamp(clock())
            require(checked >= current and
                    checked.astimezone(ZoneInfo("America/New_York")).date().isoformat() == today
                    and checked < session_close, "PIPELINE_PUBLICATION_WINDOW_CHANGED")
            return checked
        manifest = {}
        for name, raw in result["files"].items():
            digest = sha256(raw).hexdigest()
            path = "files/"+digest+".bin"
            existing = run_directory/path
            reference = (dict(path=existing.relative_to(root).as_posix(), sha256=digest)
                         if existing.exists() and existing.read_bytes() == raw else save(path, raw))
            manifest[name] = reference
        receipt = result["receipt"]
        require(receipt.get("release_sha256") == json.loads(pinned(root,config["parent_reference"])).get("release_sha256"),
                "PIPELINE_POLICY_CHANGED")
        publication_check()
        receipt_reference = save("receipt.json", receipt)
        manifest_reference = save("source-paths.json", manifest)
        finished = publication_check()
        terminal = dict(status="DAILY_CONDITIONAL_PACKET_SAVED", session=today,
            configuration_sha256=configuration_sha256, receipt_reference=receipt_reference,
            manifest_reference=manifest_reference, finished_at=finished.isoformat(),
            source_authenticated=False, coverage_complete=False, policy_approved=False,
            account_mutated=False, http_calls=captured.get("http_calls"))
    except Exception as error:
        terminal = dict(status="NEEDS_RECOVERY", session=today, reason=str(error),
            error_type=type(error).__name__, configuration_sha256=configuration_sha256,
            finished_at=stamp(clock()).isoformat(), capture_result=captured,
            policy_approved=False, account_mutated=False,
            http_calls=captured.get("http_calls") if isinstance(captured, dict) else None,
            http_calls_status="REPORTED" if isinstance(captured, dict) and "http_calls" in captured else "UNKNOWN")
    save("terminal.json", terminal)
    return terminal
