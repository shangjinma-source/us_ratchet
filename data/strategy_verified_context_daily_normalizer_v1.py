"""Versioned shared raw continuity body; leaves account/target binding to static wrappers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import pinned, require, stamp, reject_links, validate_identity_binding
from scripts.current_research_official_alert_capture import parse_official_feed, URL
from data.strategy_account_notice_review import review_notices
from data.current_quantity_v2_paper_action_sources import daily_url

NORMALIZATION_CODE_PATHS = {
    "data/strategy_daily_continuity_normalizer.py", "data/strategy_daily_session_capture.py",
    "data/strategy_daily_evidence_rebind.py", "data/strategy_daily_evidence_adapter.py",
    "data/current_quantity_v2_paper_action_sources.py",
    "scripts/current_research_official_alert_capture.py",
    "core/strategy_account_ledger.py", "core/strategy_account_difference.py",
    "data/strategy_verified_context_daily_normalizer_v1.py",
    "data/strategy_verified_context_daily_capture_v1.py", "data/strategy_account_notice_review.py",
}


def derive_identity_binding(*, root, parent_reference, security_id):
    parent = json.loads(pinned(root, parent_reference))
    closure = {name:pinned(root, dict(path=name, sha256=digest))
               for name,digest in parent["source_sha256"].items()}
    inputs = json.loads(closure[parent["normalized_inputs_path"]])
    history = inputs["histories"][security_id]
    meta = json.loads(closure[history["source_reference"]])["chart"]["result"][0]["meta"]
    security = dict(security_id=security_id, ticker=meta["symbol"],
                    **{key:meta[key] for key in ("currency","exchangeName","instrumentType")})
    binding = dict(schema="SERVER_CAPTURE_IDENTITY_V1", review_status="DERIVED_FROM_REVIEWED_PARENT",
                   security=security, parent_reference=parent_reference, new_identity_approval=False)
    validate_identity_binding(root, binding, security)
    return canonical(binding)


def extend_reviewed_calendar(*, root, previous, extension):
    """Materialize already saved schedules, checking their source closure/overlap."""
    old = json.loads(pinned(root, previous))
    extra = json.loads(pinned(root, extension))
    require(old["schema"] == "FIXED_EXCHANGE_SESSIONS_V1"
            and extra["schema"] == "SCHEDULED_REGULAR_SESSIONS_V1", "CALENDAR_SCHEMAS")
    for path, digest in extra["source_hashes"].items():
        pinned(root, dict(path=path, sha256=digest))
    sessions = {row["date"]: row for row in old["sessions"]}
    require(extra["calendar"] == [row["date"] for row in extra["sessions"]], "CALENDAR_EXTENSION_DATES")
    overlap = 0
    for row in extra["sessions"]:
        converted = dict(date=row["date"], open=row["open_at"], close=row["close_at"])
        if row["date"] in sessions:
            overlap += 1
            require(all(stamp(sessions[row["date"]][key]) == stamp(converted[key])
                        for key in ("open", "close")), "CALENDAR_OVERLAP_CHANGED")
        sessions[row["date"]] = converted
    require(overlap > 0, "CALENDAR_OVERLAP_REQUIRED")
    return canonical(dict(schema="FIXED_EXCHANGE_SESSIONS_V1", exchange="NASDAQ",
        review_status="DERIVED_FROM_PINNED_REVIEWED_SCHEDULES",
        source_references=[previous, extension],
        sessions=[sessions[day] for day in sorted(sessions)],
        actual_unscheduled_closure_coverage_complete=False))


def normalize_verified_capture(*, root, capture_directory, expected_configuration_sha256,
                            parent_reference, clock=None):
    """Returns a closed byte bundle for create-only publication by the caller.

    A normal result is conditional source continuity, not vendor authentication
    or policy authorization. Failures return no candidate receipt.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    began = stamp(clock())
    try:
        return _normalize(root=root, capture_directory=capture_directory,
            expected_configuration_sha256=expected_configuration_sha256,
            parent_reference=parent_reference,
            clock=clock, began=began)
    except (ValueError, KeyError, TypeError, OSError, IndexError, ArithmeticError) as error:
        return dict(status="WAIT_CONTINUITY_REVIEW", reason=str(error),
                    receipt=None, files=None, account_mutated=False, policy_approved=False)


def _normalize(*, root, capture_directory, expected_configuration_sha256,
               parent_reference, clock, began):
    from pathlib import Path
    import re
    reject_links(root)
    root = Path(root).resolve()
    directory = root / capture_directory
    reject_links(directory)
    directory = directory.resolve()
    require(directory.is_relative_to(root), "CAPTURE_OUTSIDE_ROOT")
    files = {}
    def read(path, digest=None):
        candidate = root / path
        reject_links(candidate)
        candidate = candidate.resolve()
        require(candidate.is_relative_to(root) and candidate.is_file(), "SOURCE_PATH_INVALID")
        require(candidate.stat().st_size <= 32*1024*1024, "SOURCE_TOO_LARGE")
        raw = candidate.read_bytes()
        require(digest is None or sha256(raw).hexdigest() == digest, "SOURCE_HASH_CHANGED")
        files[candidate.relative_to(root).as_posix()] = raw
        require(len(files) <= 2000 and sum(map(len, files.values())) <= 32*1024*1024, "SOURCE_BUDGET")
        return raw
    def capture(name):
        return read((directory / name).relative_to(root))
    config = json.loads(read((directory / "configuration.json").relative_to(root), expected_configuration_sha256))
    require(config["schema"] == "SERVER_DAILY_SESSION_CAPTURE_V1", "CAPTURE_CONFIG_SCHEMA")
    require(NORMALIZATION_CODE_PATHS <=
            {r["path"] for r in config["source_pins"]}, "NORMALIZER_SOURCE_PIN_REQUIRED")
    for reference in config["source_pins"]:
        raw_code = read(reference["path"], reference["sha256"])
        if reference["path"] in NORMALIZATION_CODE_PATHS:
            require((Path(__file__).resolve().parents[1]/reference["path"]).read_bytes() == raw_code,
                    "EXECUTING_NORMALIZER_SOURCE_CHANGED")
    calendar_raw = read(config["calendar"]["path"], config["calendar"]["sha256"])
    require(capture("calendar.json") == calendar_raw, "CAPTURE_CALENDAR_CHANGED")
    calendar = json.loads(calendar_raw)
    sessions = calendar["sessions"]
    require(calendar["schema"] == "FIXED_EXCHANGE_SESSIONS_V1" and calendar["exchange"] == "NASDAQ", "CALENDAR_SCHEMA")
    dates = [s["date"] for s in sessions]
    require(dates == sorted(set(dates)), "CALENDAR_DATES")
    for i, row in enumerate(sessions):
        opened, closed = stamp(row["open"]), stamp(row["close"])
        require(opened < closed and (i == 0 or stamp(sessions[i-1]["close"]) < opened)
                and opened.astimezone(ZoneInfo("America/New_York")).date().isoformat() ==
                row["date"] == closed.astimezone(ZoneInfo("America/New_York")).date().isoformat(), "CALENDAR_SESSION")
    today = began.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    require(today in dates and dates.index(today) >= 20, "WAIT_CALENDAR_SESSION")
    index = dates.index(today)
    window = sessions[index-20:index]
    require(began < stamp(sessions[index]["close"]), "WAIT_NEW_SESSION_EVIDENCE")
    intent, terminal = json.loads(capture("intent.json")), json.loads(capture("terminal.json"))
    require(intent["session"] == terminal["session"] == today and
            intent["configuration_sha256"] == expected_configuration_sha256, "CAPTURE_SESSION_MISMATCH")
    require(terminal["status"] == "CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED"
            and terminal["http_calls"] == 2, "CAPTURE_NOT_COMPLETE")
    require(stamp(intent["started_at"]) <= stamp(terminal["finished_at"]) <= began, "CAPTURE_TERMINAL_TIME")
    require(intent["expected_dates"] == [s["date"] for s in window]
            and stamp(intent["market_asof"]) == stamp(window[-1]["close"]), "CAPTURE_WINDOW_CHANGED")
    source_receipts, raw = {}, {}
    for name in ("daily", "official"):
        receipt = json.loads(capture(name + ".receipt.json"))
        body = capture(name + ".response.bin")
        require(receipt == terminal["results"][name] and receipt["status"] == "CAPTURED"
                and receipt["attempts"] == 1 and receipt["http_status"] == 200
                and receipt["raw_sha256"] == sha256(body).hexdigest()
                and receipt["stored_bytes"] == len(body), "CAPTURE_RECEIPT_CHANGED")
        require(stamp(window[-1]["close"]) <= stamp(intent["started_at"]) <= stamp(receipt["started_at"]) <=
                stamp(receipt["received_at"]) <= stamp(terminal["finished_at"]) <= began and
                stamp(receipt["received_at"]).astimezone(ZoneInfo("America/New_York")).date().isoformat() == today,
                "CAPTURE_CLOCK_INVALID")
        expected_url = daily_url(config["security"]["ticker"], stamp(window[0]["open"])-timedelta(days=1),
                                 stamp(receipt["started_at"])) if name == "daily" else URL
        require(receipt["url"] == expected_url, "CAPTURE_SOURCE_URL_CHANGED")
        source_receipts[name], raw[name] = receipt, body
    identity_raw = read(config["identity_review"]["path"], config["identity_review"]["sha256"])
    require(identity_raw == capture("identity-review.source"), "IDENTITY_SOURCE_CHANGED")
    security = config["security"]
    identity = json.loads(identity_raw)
    validate_identity_binding(root, identity, security)
    parent_raw = read(parent_reference["path"], parent_reference["sha256"])
    parent = json.loads(parent_raw)
    require(parent.get("schema") == "SERVER_REVIEWED_DAILY_EVIDENCE_V1"
            and parent.get("normalization_reviewed") is True and parent.get("unresolved_units") == []
            and parent.get("pending_rights") == [], "REVIEWED_PARENT_REQUIRED")
    for name, digest in parent["source_sha256"].items():
        read(name, digest)
    previous = json.loads(files[parent["normalized_inputs_path"]])
    sid = security["security_id"]
    require(sid in previous["histories"], "WAIT_NEW_SECURITY_EVIDENCE")
    old_history = previous["histories"][sid]
    require(old_history["units"]["schema"] == "REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1"
            and old_history["units"]["currency"] == security["currency"] == "USD", "UNIT_BASIS_CHANGED")
    require(old_history["units"]["basis_id"] == previous["base_target"]["price_units"][sid]
            and old_history["units"]["unit_asof"] == previous["signal_date"], "UNIT_BASIS_CHANGED")
    require(stamp(parent["available_at"]) <= began and previous["signal_date"] <= window[-1]["date"],
            "PARENT_REVIEW_IN_FUTURE")
    series = json.loads(raw["daily"])["chart"]["result"]
    require(len(series) == 1, "SOURCE_SERIES_COUNT")
    series = series[0]
    require(series["meta"]["symbol"] == security["ticker"] and all(
        series["meta"].get(key) == security[key] for key in ("currency", "exchangeName", "instrumentType")),
        "SOURCE_IDENTITY_CHANGED")
    require(not series.get("events"), "WAIT_KNOWN_ACTION_REVIEW")
    timestamps = series["timestamp"]
    closes = series["indicators"]["quote"][0]["close"]
    adjusted = series["indicators"]["adjclose"][0]["adjclose"]
    require(len(timestamps) == len(closes) == len(adjusted), "SOURCE_ARRAY_LENGTH")
    current = {}
    for ts, close, adj in zip(timestamps, closes, adjusted):
        day = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if day not in intent["expected_dates"]:
            continue
        require(day not in current and close == adj and Fraction(str(close)) > 0, "WAIT_PRICE_OR_ADJUSTMENT_REVIEW")
        current[day] = str(close)
    require(sorted(current) == intent["expected_dates"], "WAIT_COMPLETE_TWENTY_SESSIONS")
    old = {r["date"]: r["close"] for r in old_history["closes"]}
    overlap = sorted(set(old) & set(current))
    require(overlap and all(Fraction(old[d]) == Fraction(current[d]) for d in overlap), "WAIT_PRICE_CONTINUITY_REVIEW")
    feed = parse_official_feed(raw["official"], observed_at=stamp(source_receipts["official"]["received_at"]))
    require(not feed['channel']['publication_time_issue'] and not feed['channel']['future_publication']
            and all(not item['publication_time_issue'] for item in feed['items']), 'WAIT_OFFICIAL_SOURCE_TIME_REVIEW')
    names=[series['meta'][k].strip() for k in ('longName','shortName') if isinstance(series['meta'].get(k),str) and len(series['meta'][k].strip())>=2]
    notices=review_notices(raw['official'],ticker=security['ticker'],issuer_names=names)
    require(not notices['blocking'],'WAIT_KNOWN_ACTION_REVIEW')
    # Inspect already reviewed action records as well as today's limited sources.
    for name in parent["source_sha256"]:
        if name.endswith(".json"):
            record = json.loads(files[name])
            for event in record.get("distribution_events", []) if isinstance(record, dict) else []:
                if sid in (event.get("child_sid"), event.get("parent_sid"), event.get("post_parent_sid")):
                    require(not window[0]["date"] <= event["effective_date"] <= today, "WAIT_KNOWN_ACTION_REVIEW")
    prefix = "daily-normalized/" + today + "/" + sha256(raw["daily"]).hexdigest()
    unit_name, normalized_name = prefix+"/units.json", prefix+"/normalized.json"
    unit_review = dict(status="CONDITIONAL_MACHINE_CONTINUITY_CHECKED", parent_review_sha256=parent_reference["sha256"],
        overlap_exact_dates=overlap, source_authenticated=False, coverage_complete=False,
        policy_approved=False, limitations="Finite public known-action checks may miss events.")
    files[unit_name] = canonical(unit_review)
    normalized = deepcopy(previous)
    normalized.update(signal_date=window[-1]["date"], observed_at=window[-1]["close"],
        session_dates=dates[:index], session_close_times=dict(review_reference=config["calendar"]["path"],
        closes={s["date"]:s["close"] for s in sessions[:index]}))
    units = deepcopy(old_history["units"])
    units.update(unit_asof=window[-1]["date"], review_reference=unit_name)
    normalized["histories"] = {sid:dict(units=units,
        source_reference=(directory/"daily.response.bin").relative_to(root).as_posix(),
        closes=[dict(date=s["date"], close=current[s["date"]], completed_at=s["close"]) for s in window])}
    files[normalized_name] = canonical(normalized)
    finished = stamp(clock())
    require(began <= finished < stamp(sessions[index]["close"]), "NORMALIZATION_TIME_INVALID")
    receipt = deepcopy(parent)
    receipt.update(normalized_inputs_path=normalized_name, market_asof=window[-1]["close"],
        source_received_at=max(stamp(r["received_at"]) for r in source_receipts.values()).isoformat(),
        available_at=finished.isoformat(), available_at_semantics="ACTUAL_MACHINE_CONTINUITY_CHECK_FINISH",
        execution_session=sessions[index], valid_from=max(finished,stamp(sessions[index]["open"])).isoformat(),
        valid_until=sessions[index]["close"], source_authenticated=False, coverage_complete=False,
        normalization_reviewed=True, normalization_kind="CONDITIONAL_MACHINE_CONTINUITY",
        raw_source_paths=[(directory/(name+".response.bin")).relative_to(root).as_posix() for name in ("daily","official")],
        parent_review_sha256=parent_reference["sha256"],
        source_sha256={name:sha256(body).hexdigest() for name,body in files.items()})
    return dict(status='CONDITIONAL_HISTORY_READY_NOT_ACCOUNT_ADMITTED',receipt=receipt,files=files,
        account_mutated=False,policy_approved=False)
