"""Derive a 2026-only candidate from previously saved official schedule evidence.

No network, scheduler update, policy approval or extension into projected 2027.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_continuity_normalizer import extend_reviewed_calendar
from data.strategy_daily_session_capture import pinned, stamp


def prepare(root, *, write=False):
    root = Path(root).resolve()
    source_path = "tmp/forward_regular_calendar_20261016_v1/schedule.json"
    evidence_path = "tmp/forward_regular_calendar_20261016_v1/receipt.json"
    source_bytes = (root/source_path).read_bytes()
    evidence = json.loads((root/evidence_path).read_bytes())
    require(evidence["calendar_sha256"] == sha256(source_bytes).hexdigest(),
            "SAVED_CALENDAR_RECEIPT_MISMATCH")
    schedule = json.loads(source_bytes)
    require(schedule["schema"] == "SCHEDULED_REGULAR_SESSIONS_V1", "SAVED_SCHEDULE_REQUIRED")
    for path, digest in schedule["source_hashes"].items():
        pinned(root, dict(path=path, sha256=digest))
    previous_path = "research_contracts/daily_source_pipeline_20261020_v2/calendar.json"
    previous = dict(path=previous_path, sha256=sha256((root/previous_path).read_bytes()).hexdigest())
    rows = [row for row in schedule["sessions"] if row["date"] <= "2026-12-31"]
    require(rows and rows[-1]["date"] == "2026-12-31"
            and all(row["date"].startswith("2026-") for row in rows), "ONLY_2026_ALLOWED")
    early = [row["date"] for row in rows if row["early_close"]]
    require(early == ["2026-11-27", "2026-12-24"], "SAVED_EARLY_CLOSE_MISMATCH")
    output = root/"research_contracts/daily_calendar_2026_extension_v1"
    filtered_path = (output/"schedule.candidate.json").relative_to(root).as_posix()
    filtered = dict(schema=schedule["schema"], calendar=[row["date"] for row in rows],
        sessions=rows, start=rows[0]["date"], end=rows[-1]["date"],
        status="PUBLISHED_SCHEDULE_PROJECTION_NOT_FUTURE_FACT",
        scope="2026 subset only; Nasdaq official schedule matched saved NYSE schedule",
        source_hashes={**schedule["source_hashes"],
            source_path:sha256(source_bytes).hexdigest(),
            evidence_path:sha256((root/evidence_path).read_bytes()).hexdigest(),
            "scripts/prepare_daily_calendar_2026_extension.py":sha256(Path(__file__).read_bytes()).hexdigest()})
    filtered_bytes = canonical(filtered)
    report = dict(status="CANDIDATE_NOT_INSTALLED", start=rows[0]["date"],
        end=rows[-1]["date"], early_close_dates=early, network_requests=0,
        scheduler_changed=False, future_unscheduled_closures_certified=False)
    if not write:
        return report
    output.mkdir(parents=True, exist_ok=False)
    (output/"schedule.candidate.json").write_bytes(filtered_bytes)
    extension = dict(path=filtered_path, sha256=sha256(filtered_bytes).hexdigest())
    merged = extend_reviewed_calendar(root=root, previous=previous, extension=extension)
    original = json.loads((root/previous_path).read_bytes())["sessions"]
    merged_rows = json.loads(merged)["sessions"]
    by_day = {row["date"]: row for row in merged_rows}
    require(all(all(stamp(row[key]) == stamp(by_day[row["date"]][key])
                    for key in ("open", "close")) for row in original), "EXISTING_SESSIONS_CHANGED")
    (output/"calendar.candidate.json").write_bytes(merged)
    report.update(sessions=len(merged_rows), calendar_sha256=sha256(merged).hexdigest(),
                  previous=previous, extension=extension, existing_sessions_unchanged=True)
    (output/"receipt.json").write_bytes(canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.root, write=arguments.write), ensure_ascii=False))
