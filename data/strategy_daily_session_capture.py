"""Create-only daily source collection. Never approves units or a policy release."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import math
import os
import re


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode()


def stamp(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    require(isinstance(value, datetime) and value.tzinfo is not None, "AWARE_CLOCK_REQUIRED")
    return value.astimezone(timezone.utc)


def pinned(root, reference):
    candidate = root / reference["path"]
    reject_links(candidate)
    path = candidate.resolve()
    require(path.is_relative_to(root) and path.is_file(), "SOURCE_PATH_INVALID")
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == reference["sha256"], "SOURCE_HASH_CHANGED")
    return raw


def reject_links(path):
    """Reject any existing symlink or Windows reparse component before resolve."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not part.is_symlink() and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "PATH_ALIAS_FORBIDDEN")


def validate_identity_binding(root, identity, security):
    require(identity.get("schema") == "SERVER_CAPTURE_IDENTITY_V1"
            and identity.get("security") == security, "IDENTITY_REVIEW_REQUIRED")
    if identity.get("review_status") == "DERIVED_FROM_REVIEWED_PARENT":
        parent = json.loads(pinned(root, identity["parent_reference"]))
        require(parent.get("normalization_reviewed") is True
                and parent.get("unresolved_units") == [] and parent.get("pending_rights") == [],
                "IDENTITY_PARENT_NOT_REVIEWED")
        closure = {name:pinned(root, dict(path=name, sha256=digest))
                   for name,digest in parent["source_sha256"].items()}
        inputs = json.loads(closure[parent["normalized_inputs_path"]])
        history = inputs["histories"][security["security_id"]]
        require(history["units"]["currency"] == security["currency"] == "USD", "IDENTITY_CURRENCY_CHANGED")
        meta = json.loads(closure[history["source_reference"]])["chart"]["result"][0]["meta"]
        require(meta["symbol"] == security["ticker"] and all(
            meta[key] == security[key] for key in ("currency", "exchangeName", "instrumentType")),
            "IDENTITY_PARENT_MAPPING_CHANGED")
    else:
        require(identity.get("review_status") == "REVIEWED", "IDENTITY_REVIEW_REQUIRED")


def capture_session(*, root, configuration_bytes, configuration_sha256, execute=False,
                    fetch_daily=None, fetch_official=None, clock=None):
    """Config is server-owned pinned bytes; CLI never accepts a synthetic clock.

    A claimed session directory is never re-used, including after transport or
    review failure. Operators must diagnose preserved evidence before recovery.
    """
    reject_links(root)
    root = Path(root).resolve()
    require(sha256(configuration_bytes).hexdigest() == configuration_sha256, "CONFIG_HASH_CHANGED")
    config = json.loads(configuration_bytes)
    require(config["schema"] == "SERVER_DAILY_SESSION_CAPTURE_V1", "CONFIG_SCHEMA")
    require({r["path"] for r in config["source_pins"]} >= {
        "data/strategy_daily_session_capture.py", "data/current_quantity_v2_paper_action_sources.py",
        "scripts/current_research_official_alert_capture.py"}, "SOURCE_PINS_REQUIRED")
    for reference in config["source_pins"]:
        pinned(root, reference)
    calendar_raw = pinned(root, config["calendar"])
    identity_raw = pinned(root, config["identity_review"])
    identity = json.loads(identity_raw)
    validate_identity_binding(root, identity, config["security"])
    calendar = json.loads(calendar_raw)
    require(calendar["schema"] == "FIXED_EXCHANGE_SESSIONS_V1" and calendar["exchange"] == "NASDAQ", "CALENDAR_SCHEMA")
    sessions = calendar["sessions"]
    dates = [s["date"] for s in sessions]
    require(len(dates) == len(set(dates)) and dates == sorted(dates), "CALENDAR_ORDER")
    for session in sessions:
        require(stamp(session["open"]) < stamp(session["close"]), "CALENDAR_SESSION")
        require(stamp(session["open"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()
                == session["date"] == stamp(session["close"]).astimezone(ZoneInfo("America/New_York")).date().isoformat(),
                "CALENDAR_SESSION_DATE")
    current = stamp((clock or (lambda: datetime.now(timezone.utc)))())
    today = current.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    if today not in dates:
        return dict(status="WAIT_CALENDAR_SESSION", session=today, http_calls=0)
    index = dates.index(today)
    if index < 20:
        return dict(status="WAIT_COMPLETE_CALENDAR_WINDOW", session=today, http_calls=0)
    window = sessions[index-20:index]
    if current >= stamp(sessions[index]["close"]):
        return dict(status="WAIT_NEXT_SESSION", session=today, http_calls=0)
    require(all(stamp(s["close"]) <= current for s in window), "INCOMPLETE_MARKET_WINDOW")
    security = config["security"]
    require(re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", security["ticker"]) is not None, "TICKER_INVALID")
    require(security["currency"] == "USD" and security["exchangeName"] == "NMS"
            and security["instrumentType"] == "EQUITY" and security["security_id"], "IDENTITY_CONFIG")
    reject_links(root / config["output_root"])
    base = (root / config["output_root"]).resolve()
    require(base.is_relative_to(root) and base != root, "OUTPUT_OUTSIDE_ROOT")
    output = base / today
    reject_links(output)
    if output.exists():
        return dict(status="EXISTING_CAPTURE_REQUIRES_RECEIPT_REVIEW", session=today,
                    output=str(output), http_calls=0)
    intent = dict(schema="DAILY_SESSION_CAPTURE_INTENT_V1", session=today,
                  expected_dates=[s["date"] for s in window], market_asof=window[-1]["close"],
                  configuration_sha256=configuration_sha256, started_at=current.isoformat(),
                  security=security, maximum_requests=2, automatic_retry=False,
                  policy_approved=False, source_authenticated=False, coverage_complete=False)
    if not execute:
        return dict(intent, status="DRY_RUN_NO_HTTP_NO_FILES", output=str(output), http_calls=0)
    output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        with (output / name).open("xb") as stream:
            stream.write(value if isinstance(value, bytes) else encoded(value))
    save("intent.json", intent)
    save("configuration.json", configuration_bytes)
    save("calendar.json", calendar_raw)
    save("identity-review.source", identity_raw)
    from data.current_quantity_v2_paper_action_sources import fetch_daily_actions, daily_url
    from scripts.current_research_official_alert_capture import fetch_official_feed, URL, parse_official_feed
    clock = clock or (lambda: datetime.now(timezone.utc))
    start = stamp(window[0]["open"]) - timedelta(days=1)
    results, raw_bodies, http_calls = {}, {}, 0
    for name in ("daily", "official"):
        began = stamp(clock())
        receipt = dict(started_at=began.isoformat(), attempts=0)
        try:
            require(began >= current, "CLOCK_MOVED_BACKWARDS")
            require(began.astimezone(ZoneInfo("America/New_York")).date().isoformat() == today
                    and began < stamp(sessions[index]["close"]), "CAPTURE_OUTSIDE_SESSION_DAY")
            expected_url = daily_url(security["ticker"], start, began) if name == "daily" else URL
            http_calls += 1
            receipt["attempts"] = 1
            response = ((fetch_daily or fetch_daily_actions)(security["ticker"], start, began)
                        if name == "daily" else (fetch_official or fetch_official_feed)())
            received = stamp(clock())
            body = response["body"]
            require(type(body) is bytes, "SOURCE_BYTES_REQUIRED")
            save(name + ".response.bin", body)
            receipt.update(received_at=received.isoformat(), raw_sha256=sha256(body).hexdigest(),
                           http_status=response["status"], url=expected_url, stored_bytes=len(body))
            require(current <= began <= received, "CLOCK_MOVED_BACKWARDS")
            require(received.astimezone(ZoneInfo("America/New_York")).date().isoformat() == today
                    and received < stamp(sessions[index]["close"]), "CAPTURE_OUTSIDE_SESSION_DAY")
            require(response.get("url", expected_url) == expected_url, "SOURCE_URL_CHANGED")
            require(response["status"] == 200 and 0 < len(body) <= (4194304 if name == "daily" else 2097152), "TRANSPORT_FAILED")
            raw_bodies[name] = body
            receipt["status"] = "CAPTURED"
        except Exception as error:
            receipt.update(status="FAILED_PRESERVED", error_type=type(error).__name__, error=str(error),
                           failure_observed_at=stamp(clock()).isoformat())
        save(name + ".receipt.json", receipt)
        results[name] = receipt
    terminal = dict(status="WAIT_SOURCE_REVIEW", session=today, http_calls=http_calls, results=results,
                    source_authenticated=False, coverage_complete=False, policy_approved=False,
                    account_mutated=False, automatic_retry=False)
    try:
        require(len(raw_bodies) == 2, "CAPTURE_FAILED_PRESERVED")
        result = json.loads(raw_bodies["daily"])["chart"]["result"]
        require(len(result) == 1, "DAILY_RESULT_COUNT")
        series = result[0]
        meta = series["meta"]
        require(all(meta.get(key) == security[key] for key in
                    ("currency", "exchangeName", "instrumentType")), "IDENTITY_MISMATCH")
        require(meta.get("symbol") == security["ticker"], "TICKER_MISMATCH")
        quotes = series["indicators"]["quote"][0]["close"]
        adjusted = series["indicators"]["adjclose"][0]["adjclose"]
        times = series["timestamp"]
        require(len(times) == len(quotes) == len(adjusted), "DAILY_ARRAY_LENGTH")
        observed = {}
        for ts, close, adj in zip(times, quotes, adjusted):
            date = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            if date not in intent["expected_dates"]:
                continue  # Current unfinished daily candle is never used.
            require(date not in observed and type(close) in (int, float)
                    and math.isfinite(close) and close > 0, "DAILY_PRICE_INVALID")
            require(close == adj, "WAIT_ADJUSTMENT_REVIEW")
            observed[date] = close
        require(sorted(observed) == intent["expected_dates"], "WAIT_COMPLETE_TWENTY_SESSIONS")
        feed = parse_official_feed(raw_bodies["official"],
                                  observed_at=stamp(results["official"]["received_at"]))
        matches = [r for r in feed["items"] if re.search(
            r"\b" + re.escape(security["ticker"]) + r"\b", r["title"] + " " + r["description_summary"], re.I)
            or (security["ticker"] == "SNDK" and r["title_match_candidate"])]
        require(not feed["channel"]["future_publication"]
                and not any(r["future_publication"] for r in feed["items"]), "WAIT_OFFICIAL_SOURCE_TIME_REVIEW")
        require(not series.get("events") and not matches, "WAIT_KNOWN_ACTION_REVIEW")
        save("candidate.json", dict(schema="UNREVIEWED_DAILY_WINDOW_V1", security=security,
             execution_session=today, market_asof=intent["market_asof"],
             closes=observed, source_received_at=max(r["received_at"] for r in results.values()),
             unit_review_required=True, source_authenticated=False, coverage_complete=False,
             policy_approved=False))
        terminal["status"] = "CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED"
    except Exception as error:
        terminal.update(status="WAIT_SOURCE_REVIEW", reason=str(error), error_type=type(error).__name__)
    terminal["finished_at"] = stamp(clock()).isoformat()
    save("terminal.json", terminal)
    return dict(terminal, output=str(output))
