"""Offline dates-only schedule from pinned local 2024-2026 exchange evidence."""
import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path

REVIEW = "tmp/old_window_official_calendar_20261026/review.json"
REVIEW_SHA = "195c2770e98c7eb613aa5bca72bbfa350cd725670de5bd71677be3cebcf55c83"
RUNTIME = "research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json"
RUNTIME_SHA = "1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af"
SUPPORTED_YEARS = {2024, 2025, 2026}  # Explicit years of the pinned NYSE PDF.


def checked_read(root, name, expected, pins):
    name = name.replace("\\", "/")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("SOURCE_OUTSIDE_ROOT")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError("SOURCE_HASH_CHANGED:" + name)
    pins[name] = expected
    return raw


def schedule_dates(start, end, holidays, runtime_dates):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if start > end or not set(range(start.year, end.year + 1)) <= SUPPORTED_YEARS:
        raise ValueError("OFFICIAL_YEAR_COVERAGE_UNAVAILABLE")
    if runtime_dates != sorted(set(runtime_dates)) or not runtime_dates:
        raise ValueError("RUNTIME_DATES_INVALID")
    dates = []
    day = start
    while day <= end:
        if day.weekday() < 5 and day.isoformat() not in holidays:
            dates.append(day.isoformat())
        day += timedelta(days=1)
    lower, upper = max(start.isoformat(), runtime_dates[0]), min(end.isoformat(), runtime_dates[-1])
    if lower > upper:
        raise ValueError("NO_RUNTIME_CALENDAR_INTERSECTION")
    expected = [d for d in runtime_dates if lower <= d <= upper]
    if [d for d in dates if lower <= d <= upper] != expected:
        raise ValueError("RUNTIME_CALENDAR_INTERSECTION_MISMATCH")
    return dates, dict(start=lower, end=upper, count=len(expected))


def build(root, start, end):
    root = Path(root).resolve()
    pins = {}
    review = json.loads(checked_read(root, REVIEW, REVIEW_SHA, pins))
    for name, expected in review["source_hashes"].items():
        checked_read(root, name, expected, pins)
    runtime = json.loads(checked_read(root, RUNTIME, RUNTIME_SHA, pins))
    if runtime["schema"] != "FIXED_EXCHANGE_SESSIONS_V1":
        raise ValueError("RUNTIME_SCHEMA_INVALID")
    for reference in runtime["source_references"]:
        document = json.loads(checked_read(root, reference["path"], reference["sha256"], pins))
        # Recheck the extension's official capture chain, not unrelated historical research.
        if document.get("schema") == "SCHEDULED_REGULAR_SESSIONS_V1":
            for name, expected in document["source_hashes"].items():
                checked_read(root, name, expected, pins)
    dates, intersection = schedule_dates(start, end, set(review["full_holidays"]),
                                         [row["date"] for row in runtime["sessions"]])
    return dict(schema="VERIFIED_SCHEDULE_DATES_V1", sessions=[dict(date=d) for d in dates],
                start=start, end=end, official_source_years=sorted(SUPPORTED_YEARS),
                runtime_intersection=intersection,
                source_references=[dict(path=p, sha256=h) for p, h in sorted(pins.items())],
                actual_unscheduled_closure_coverage_complete=False,
                explicit_special_closures=["2025-01-09"],
                method="Weekdays minus pinned official full holidays; early closes remain trading dates. No intraday times inferred.",
                limitations=["Scheduled dates, not proof of future actual trading or exhaustive temporary closure notices.",
                             "Only the reviewed Carter closure supplements scheduled holidays. No market prices or month selections generated."])


def write_immutable(path, result):
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("OUTPUT_ALREADY_EXISTS_DIFFERENT")
    return sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-12-31")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build(Path(__file__).resolve().parents[2], args.start, args.end)
    digest = write_immutable(args.output, result)
    print(json.dumps(dict(path=args.output, sha256=digest, sessions=len(result["sessions"]),
                         runtime_intersection=result["runtime_intersection"])))


if __name__ == "__main__":
    main()
