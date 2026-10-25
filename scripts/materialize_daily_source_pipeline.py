"""Materialize derived saved-evidence configuration; no HTTP or policy approval."""
from hashlib import sha256
import argparse
import json
from pathlib import Path

from core.strategy_account_ledger import canonical
from data.strategy_daily_continuity_normalizer import (
    derive_identity_binding, extend_reviewed_calendar, NORMALIZATION_CODE_PATHS,
)
from data.strategy_daily_source_runner import RUNNER_CODE_PATHS
from data.strategy_daily_session_capture import reject_links, require, pinned

PARENT = dict(path="tmp/daily_signal_sndk_reviewed_20261020_v1/receipt.json",
    sha256="630a006930b25efb489b2a3b93742857397ec60edac965617e206d86a68c6ed0")
CALENDAR = dict(path="tmp/daily_signal_sndk_reviewed_20261020_v1/calendar.json",
    sha256="6739440bad35857b52254188e0e476258f11bde9952b3eaa1511ed513c57d197")
EXTENSION = dict(path="research_contracts/nasdaq_regular_session_calendar_20261013_20261102_v1.json",
    sha256="0d7b7e1e5925fe380ad8dcfc1a7e7936f3a138aebb0f80e517c80fd343392362")


def materialize(root, output):
    reject_links(root)
    root = Path(root).resolve()
    directory = root/output
    reject_links(directory)
    directory = directory.resolve()
    require(directory.is_relative_to(root) and directory != root, "CONFIG_OUTPUT_OUTSIDE_ROOT")
    identity_raw = derive_identity_binding(root=root, parent_reference=PARENT,
                                          security_id="security:0002023554:80004C200")
    calendar_raw = extend_reviewed_calendar(root=root, previous=CALENDAR, extension=EXTENSION)
    directory.mkdir(parents=True, exist_ok=False)
    def save(name, raw):
        with (directory/name).open("xb") as stream:
            stream.write(raw)
        return dict(path=(directory/name).relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
    def source(name):
        reject_links(root/name)
        return dict(path=name,sha256=sha256((root/name).read_bytes()).hexdigest())
    identity = save("identity.json", identity_raw)
    calendar = save("calendar.json", calendar_raw)
    capture = dict(schema="SERVER_DAILY_SESSION_CAPTURE_V1", identity_review=identity,
        calendar=calendar, security=json.loads(identity_raw)["security"],
        source_pins=[source(name) for name in sorted(NORMALIZATION_CODE_PATHS)],
        output_root="data/daily_source_pipeline/capture")
    capture_reference = save("capture.json", canonical(capture))
    pipeline = dict(schema="SERVER_DAILY_SOURCE_PIPELINE_V1", first_execution_date="2026-10-21",
        capture_configuration=capture_reference, parent_reference=PARENT,
        source_pins=[source(name) for name in sorted(RUNNER_CODE_PATHS)],
        runs_root="data/daily_source_pipeline/runs",
        account_database="data/strategy_account/real_strategy.sqlite3",
        target_database="data/strategy_account/monthly_targets.sqlite3",
        account_id=json.loads(pinned(root,PARENT))["account_id"],
        policy_approved=False, scheduler_installed=False)
    reference = save("pipeline.json", canonical(pipeline))
    save("materialization.json", canonical(dict(status="DERIVED_CONFIG_SAVED_NOT_SCHEDULED",
        pipeline_reference=reference, calendar_last_session="2026-11-02",
        identity_review_inherited=True, new_identity_approval=False,
        policy_approved=False, http_calls=0)))
    return reference


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    print(json.dumps(materialize(args.root,args.output)))
