"""Isolated prewarm coordinator. No scheduled task installation or CLI activation.

Callbacks are server-owned dependencies, never browser arguments. Existing paper
dispatch keeps its own registration, lock, source and final-time checks. This
helper does not make a slow existing dispatch fast or authorize missed sessions.
"""
from datetime import datetime, timezone, timedelta
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import time
from zoneinfo import ZoneInfo


def need(value, reason):
    if not value:
        raise ValueError(reason)


def stamp(value):
    need(isinstance(value, datetime) and value.tzinfo is not None, "AWARE_CLOCK_REQUIRED")
    return value.astimezone(timezone.utc)


def verify_pin_groups(root, groups):
    """Exact-path dedup only within this invocation; always reread on next call."""
    root = Path(root).absolute()
    expected = {}
    for group in groups:
        for name, digest in group.items():
            need(isinstance(name, str) and isinstance(digest, str)
                 and len(digest) == 64, "PIN_INVALID")
            path = root / name
            need(not Path(name).is_absolute() and ".." not in Path(name).parts,
                 "PIN_PATH_INVALID")
            for part in (path, *path.parents):
                need(not part.is_symlink()
                     and not getattr(part, "is_junction", lambda: False)(),
                     "PIN_LINK_REJECTED")
            resolved = path.resolve()
            need(resolved.is_relative_to(root.resolve()), "PIN_OUTSIDE_ROOT")
            need(resolved not in expected or expected[resolved] == digest,
                 "PIN_CONFLICT")
            expected[resolved] = digest
    count = 0
    for path, digest in expected.items():
        # Streaming bounds peak memory, not the admitted source domain.
        check = sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                check.update(block)
        need(check.hexdigest() == digest, "PIN_CHANGED")
        count += 1
    return {"unique_files_read": count, "cache_scope": "THIS_CALL_ONLY"}


class RegisteredPaperPrewarmValidationV1:
    """Real read-only registration adapter; nothing loaded on construction.

    Calendar is returned only after original registration validation. A future
    launcher must pin its calendar before calling run_prewarmed_session and
    compare it with this returned calendar on both validation passes.
    """
    def __init__(self, descriptor_path, expected_descriptor_sha256, *, clock=None):
        self.path = Path(descriptor_path).absolute()
        self.expected = expected_descriptor_sha256
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.automation = None

    def load_dependencies(self):
        from scripts import run_registered_paper_automation
        self.automation = run_registered_paper_automation

    def validate(self):
        need(self.automation is not None, "DEPENDENCIES_NOT_LOADED")
        automation = self.automation
        for part in (self.path, *self.path.parents):
            need(not part.is_symlink()
                 and not getattr(part, "is_junction", lambda: False)(),
                 "DESCRIPTOR_LINK_REJECTED")
        raw = self.path.read_bytes()
        need(sha256(raw).hexdigest() == self.expected, "DESCRIPTOR_CHANGED")
        descriptor = json.loads(raw)
        need(descriptor["schema"] == "REGISTERED_PAPER_AUTOMATION_V1",
             "DESCRIPTOR_SCHEMA")
        root = Path(descriptor["root"]).resolve()
        need(self.path.resolve().is_relative_to(root), "DESCRIPTOR_OUTSIDE_ROOT")
        reference = descriptor["publication_policy"]
        verify_pin_groups(root, [{reference["path"]: reference["sha256"]}])
        policy_raw = (root / reference["path"]).read_bytes()
        need(sha256(policy_raw).hexdigest() == reference["sha256"], "POLICY_CHANGED")
        policy = json.loads(policy_raw)
        need(policy["request_sha256"] == descriptor["request_sha256"]
             and policy["registration_directory"] == descriptor["registration_directory"],
             "POLICY_REGISTRATION_MISMATCH")
        result = verify_pin_groups(root, [descriptor["source_hashes"], policy["source_hashes"]])
        for name, where in automation.REQUIRED.items():
            need(descriptor["source_hashes"].get(name)
                 == sha256(Path(where()).read_bytes()).hexdigest(),
                 "EXECUTABLE_PIN_MISMATCH")
        validated = automation.runtime.load_bundle(
            root=root, registration_directory=descriptor["registration_directory"],
            expected_request_sha256=descriptor["request_sha256"], now=self.clock())
        audited = automation.runtime.audit_runtime_receipts(
            validated=validated, now=self.clock())
        # Recheck descriptor after potentially expensive bundle reads. No state
        # result is retained for dispatch; old dispatcher will read everything.
        need(sha256(self.path.read_bytes()).hexdigest() == self.expected,
             "DESCRIPTOR_CHANGED")
        return {"calendar": validated["calendar"],
                "first_decision_at": validated["first_decision_at"],
                "state_revision": audited["revision"], "source_read_summary": result,
                "account_writes": False, "strategy_dispatches": 0}

    def dispatch(self):
        need(self.automation is not None, "DEPENDENCIES_NOT_LOADED")
        return self.automation.run(descriptor_path=self.path,
                                   expected_descriptor_sha256=self.expected,
                                   mode="daily", execute=True)


def run_prewarmed_session(*, calendar, session, lock_path, load_dependencies,
                         validate_current, dispatch, emit, armed=False,
                         clock=None, monotonic=None, sleep=None):
    """Warm before today's 10:00; never pass a frozen clock to dispatch.

    calendar must already come from a separately pinned server configuration.
    validate_current must revalidate that binding, registration, source pins and
    current account receipts, without selection/capture/account writes.
    No callbacks or modules are cached across process invocations.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    calendar = deepcopy(calendar)
    monotonic = monotonic or time.monotonic
    sleep = sleep or time.sleep
    previous_wall = None
    previous_mono = None
    started_mono = monotonic()

    def now():
        nonlocal previous_wall, previous_mono
        wall, mono = stamp(clock()), monotonic()
        need(previous_wall is None or wall >= previous_wall, "CLOCK_ROLLBACK")
        need(previous_mono is None or mono >= previous_mono, "MONOTONIC_ROLLBACK")
        previous_wall, previous_mono = wall, mono
        return wall

    def stage(name):
        emit({"stage": name, "observed_at": now().isoformat(),
              "elapsed_seconds": monotonic() - started_mono})

    # This is intentionally emitted before load_dependencies imports heavy code.
    stage("ENTRY_BEFORE_IMPORT")
    rows = [row for row in calendar["sessions"] if row["date"] == session]
    need(len(rows) == 1, "FIXED_SESSION_REQUIRED")
    row = rows[0]
    opens = stamp(datetime.fromisoformat(row["open_at"]))
    closes = stamp(datetime.fromisoformat(row["close_at"]))
    decision = datetime.fromisoformat(session + "T10:00:00").replace(
        tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    deadline = decision + timedelta(minutes=1)
    need(opens <= decision < deadline <= closes, "DECISION_OUTSIDE_SESSION")
    observed = now()
    need(observed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
         == session, "NOT_CURRENT_SESSION")
    need(observed < deadline, "MISSED_DECISION_WINDOW")
    need(observed >= decision - timedelta(minutes=30), "PREWARM_TOO_EARLY")
    lock = Path(lock_path)
    for part in (lock.absolute(), *lock.absolute().parents):
        need(not part.is_symlink()
             and not getattr(part, "is_junction", lambda: False)(),
             "PREWARM_LOCK_LINK")
    # Dedicated prewarm lock, never the simulation mutation lock.
    # Parent must exist: don't manufacture production state directories.
    try:
        stream = lock.open("x", encoding="utf8")
    except FileExistsError:
        return {"status": "PREWARM_LOCK_PRESENT_REVIEW_REQUIRED", "dispatches": 0}
    token = json.dumps({"session": session, "entered_at": observed.isoformat()})
    with stream:
        stream.write(token)
        stream.flush()
    try:
        load_dependencies()
        stage("IMPORT_COMPLETE")
        validated = validate_current()
        need(isinstance(validated, dict) and validated.get("calendar") == calendar,
             "VALIDATED_CALENDAR_CHANGED")
        stage("PREWARM_READ_ONLY_VALIDATION_COMPLETE")
        if not armed:
            return {"status": "PREWARM_CHECK_ONLY", "dispatches": 0,
                    "decision_at": decision.isoformat()}
        while True:
            observed = now()
            need(observed < deadline, "MISSED_DECISION_WINDOW")
            if observed >= decision:
                break
            sleep(min(1.0, (decision - observed).total_seconds()))
        stage("FINAL_VALIDATION_STARTED")
        validated = validate_current()  # no reuse of prewarm account/target/source data
        need(isinstance(validated, dict) and validated.get("calendar") == calendar,
             "VALIDATED_CALENDAR_CHANGED")
        observed = now()    # measured after all expensive final validation
        need(decision <= observed < deadline, "MISSED_DECISION_WINDOW")
        stage("DISPATCH_STARTED")
        need(decision <= now() < deadline, "MISSED_DECISION_WINDOW")
        # dispatch must use its own real clock, and its original guarded checks.
        result = dispatch()
        stage("DISPATCH_RETURNED")
        return {"status": "DISPATCH_RETURNED", "dispatches": 1, "result": result}
    finally:
        need(lock.read_text(encoding="utf8") == token, "PREWARM_LOCK_CHANGED")
        lock.unlink()
