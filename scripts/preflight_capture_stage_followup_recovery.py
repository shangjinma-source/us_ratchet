"""Offline candidate review for a failed daily capture; never publishes or fetches."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import require
from data.current_research_saved_quote import _json, _plain
from data.strategy_daily_session_capture import reject_links
from scripts.preflight_followup_recovery import CALENDAR, CALENDAR_SHA

NY = ZoneInfo("America/New_York")


def preflight(*, root, request, now=None):
    """ADMISSIBLE_FOR_REVIEW is explicitly not evidence admission or publication."""
    references = {}
    total = 0
    def stamp(value):
        at = datetime.fromisoformat(value)
        require(at.utcoffset() is not None, "AWARE_TIME_REQUIRED")
        return at
    try:
        reject_links(root)
        root = Path(root).resolve()
        observed = now or datetime.now(timezone.utc)
        require(observed.utcoffset() is not None, "AWARE_TIME_REQUIRED")
        def read(ref):
            nonlocal total
            name, expected = ref["path"], ref["sha256"]
            relative = Path(name)
            require(not relative.is_absolute() and ".." not in relative.parts, "INVALID_PATH")
            path = root/relative
            reject_links(path)
            require(path.resolve().is_relative_to(root), "SOURCE_OUTSIDE_ROOT")
            with path.open("rb") as stream:
                raw = stream.read(8*1024*1024+1)
            total += len(raw)
            require(len(raw) <= 8*1024*1024 and total <= 64*1024*1024, "SOURCE_BUDGET")
            require(sha256(raw).hexdigest() == expected, "SOURCE_CHANGED")
            require(name not in references or references[name] == expected, "SOURCE_CONFLICT")
            references[name] = expected
            return raw
        def document(ref):
            return _json(read(ref))
        require(request["schema"] == "CAPTURE_STAGE_FOLLOWUP_REVIEW_V1", "REQUEST_SCHEMA")
        refs = request["references"]
        require(set(refs) == {"event", "started", "failed", "completion", "original_raw",
                             "original_receipt", "original_decoded", "later_raw", "later_receipt"},
                "REFERENCE_SET")
        event = document(refs["event"])
        started, failed = document(refs["started"]), document(refs["failed"])
        target = request["target_session"]
        event_hash = refs["event"]["sha256"]
        attempt = f"data/quantity_v2_followup/attempts/{event_hash}/{target}"
        require(refs["started"]["path"] == attempt+"/started.json"
                and refs["failed"]["path"] == attempt+"/failed.json", "ATTEMPT_PATH")
        require(started["status"] == "PREFLIGHT_ONLY" and started["event_sha256"] == event_hash
                and started["session"] == target, "ATTEMPT_BINDING")
        require(failed["status"] == "BLOCKED" and failed["reason"] == "DAILY_CAPTURE_FAILED"
                and failed["retry_allowed"] is False, "UNSUPPORTED_FAILURE")
        require(not (root/attempt/"complete.json").exists()
                and not (root/attempt/"review.json").exists(), "NOT_CAPTURE_STAGE_FAILURE")
        pins = request["attempt_source_hashes"]
        files = list((root/attempt).rglob("*"))
        for path in files:
            reject_links(path)
        actual = {p.relative_to(root).as_posix() for p in files if p.is_file()}
        require(actual == set(pins) and len(pins) <= 200, "ATTEMPT_CLOSURE")
        for name, digest in pins.items():
            read(dict(path=name, sha256=digest))
        require(all(pins.get(refs[k]["path"]) == refs[k]["sha256"] for k in
                    ("started", "failed", "completion", "original_raw",
                     "original_receipt", "original_decoded")), "ATTEMPT_REFERENCE_CONFLICT")
        begin, event_at, failed_at = map(stamp, (event["request_started_at"],
                                               event["observed_at"], failed["at"]))
        require(begin <= event_at <= failed_at <= observed, "EVENT_TIME")
        require(event["schema"] == "V2_GENERATED_PREVIEW_OBSERVATION_V1"
                and event["status"] == "READY" and event["actual_fill_inferred"] is False
                and event["generated_not_confirmed_displayed"] is True, "EVENT_SCHEMA")
        require(refs["event"]["path"] == "data/quantity_v2_observations/events/"
                +begin.astimezone(NY).date().isoformat()+"/"+event["event_id"]+".json",
                "EVENT_PATH")
        binding = started["binding"]
        require(binding["decision_id"] == event["decision_id"]
                and all(binding[k] == event["research_context"][k]
                        for k in ("research_version", "available_cash_exact")), "EVENT_BINDING")
        securities = started["securities"]
        require(len(securities) == 1, "SINGLE_SECURITY_REVIEW_ONLY")
        security = securities[0]
        require(security["security_type"] == "EQUITY"
                and {(o["security_id"], o["ticker"]) for o in event["orders"]}
                == {(security["security_id"], security["ticker"])}, "SECURITY_BINDING")
        for capture in event["captures"]:
            require(capture["path"] == "raw/"+capture["sha256"]+".bin"
                    and capture["security_id"] == security["security_id"]
                    and capture["ticker"] == security["ticker"], "EVENT_CAPTURE_BINDING")
            read(dict(path="data/quantity_v2_observations/"+capture["path"],
                      sha256=capture["sha256"]))
        calendar = document(dict(path=CALENDAR, sha256=CALENDAR_SHA))
        for name, digest in calendar["source_hashes"].items():
            read(dict(path=name, sha256=digest))
        dates = calendar["calendar"]
        reference_day = event_at.astimezone(NY).date().isoformat()
        require(reference_day in dates and target in dates, "CALENDAR_DATE")
        offset = dates.index(target)-dates.index(reference_day)
        require(offset in (1, 5, 20) and started["matured_horizons"]
                == [n for n in (1, 5, 20) if n <= offset], "HORIZON_BINDING")
        sessions = [r for r in calendar["sessions"] if r["date"] == target]
        require(len(sessions) == 1, "CALENDAR_SESSION")
        close = stamp(sessions[0]["close_at"])
        completion = document(refs["completion"])
        require(completion["session"] == target and len(completion["entries"]) == 1, "COMPLETION_BINDING")
        entry = completion["entries"][0]
        require(entry["ticker"] == security["ticker"] and entry["security_id"] == security["security_id"]
                and entry["status"] == "READER_VALIDATION_FAILED"
                and entry["reason"] == "INVALID_OHLC_VALUE", "FAILURE_NOT_NULL_BAR")
        for field, key in (("raw_sha256", "original_raw"), ("receipt_sha256", "original_receipt"),
                           ("decoded_sha256", "original_decoded")):
            require(entry[field] == refs[key]["sha256"], "COMPLETION_HASH")
        old_receipt, decoded = document(refs["original_receipt"]), document(refs["original_decoded"])
        old_raw, later_raw = read(refs["original_raw"]), read(refs["later_raw"])
        later_receipt = document(refs["later_receipt"])
        require(old_receipt["http_status"] == 200 and old_receipt["ticker"] == security["ticker"]
                and old_receipt["security_id"] == security["security_id"]
                and old_receipt["raw_sha256"] == sha256(old_raw).hexdigest()
                and decoded["receipt_sha256"] == refs["original_receipt"]["sha256"]
                and decoded["decoded_sha256"] == sha256(old_raw).hexdigest(), "ORIGINAL_RECEIPT")
        require(later_receipt["http_status"] == 200 and later_receipt["accepted_transport"] is True
                and later_receipt["sha256"] == sha256(later_raw).hexdigest()
                and later_receipt["bytes"] == len(later_raw), "LATER_RECEIPT")
        url = urlparse(later_receipt["url"])
        query = parse_qs(url.query)
        require(url.scheme == "https" and url.hostname == "query1.finance.yahoo.com"
                and url.path == "/v8/finance/chart/"+security["ticker"]
                and query.get("interval") == ["1d"], "LATER_SOURCE")
        old_received = stamp(old_receipt["received_at_utc"])
        received, capture_started = stamp(later_receipt["received_at"]), stamp(later_receipt["started_at"])
        require(close <= old_received <= failed_at <= capture_started <= received <= observed, "CAPTURE_TIME")
        def bar(raw, allow_null):
            chart = _json(raw)["chart"]
            require(chart["error"] is None and len(chart["result"]) == 1, "CHART_RESULT")
            channel = chart["result"][0]; meta = channel["meta"]
            require(meta["symbol"] == security["ticker"] and meta["currency"] == "USD"
                    and meta["instrumentType"] == "EQUITY"
                    and meta["exchangeTimezoneName"] == "America/New_York"
                    and meta["dataGranularity"] == "1d", "PRICE_COORDINATE")
            timestamps = channel["timestamp"]
            require(all(type(t) is int for t in timestamps)
                    and timestamps == sorted(set(timestamps)), "TIMESTAMPS")
            days = [datetime.fromtimestamp(t, NY).date().isoformat() for t in timestamps]
            require(days == sorted(set(days)) and target in days, "TARGET_BAR")
            quotes = channel["indicators"]["quote"]
            require(len(quotes) == 1 and all(len(quotes[0][k]) == len(days)
                    for k in ("open", "high", "low", "close")), "BAR_ALIGNMENT")
            result = {k: quotes[0][k][days.index(target)] for k in ("open", "high", "low", "close")}
            for value in result.values():
                require((allow_null and value is None) or
                        (not isinstance(value, bool) and isinstance(value, (int, Decimal))
                         and Decimal(value).is_finite() and value > 0), "INVALID_OHLC_VALUE")
            if not allow_null:
                require(result["low"] <= min(result["open"], result["close"])
                        <= max(result["open"], result["close"]) <= result["high"], "OHLC_RANGE")
            return result
        old, new = bar(old_raw, True), bar(later_raw, False)
        require(any(v is None for v in old.values()), "ORIGINAL_NOT_NULL_BAR")
        differences = {k: dict(original=_plain(old[k]), later=_plain(new[k]),
                              kind="MISSING_VALUE" if old[k] is None else "PROVIDER_REVISION")
                       for k in old if old[k] != new[k]}
        return dict(status="ADMISSIBLE_FOR_REVIEW", publication_allowed=False,
                    actual_fill_inferred=False, index_writes=False, http_calls=0,
                    target_session=target, security=security, binding=binding,
                    original_bar=_plain(old), later_whole_bar=_plain(new), differences=differences,
                    later_received_at=received.isoformat(), known_at_original_event=False,
                    semantics="LATER_CAPTURE_FOR_RETROSPECTIVE_REVIEW_ONLY",
                    unresolved=["EXPLICIT_WHOLE_BAR_REVISION_REVIEW", "FOLLOWUP_IDENTITY_AND_UNIT_REVIEW",
                                "FOLLOWUP_ACTION_EVIDENCE_REVIEW", "PUBLICATION_INDEX_CAS_REVIEW"],
                    source_hashes=references)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        return dict(status="BLOCKED", reason=str(error), publication_allowed=False,
                    http_calls=0, index_writes=False, source_hashes=references)
