"""Bounded real-clock verification before returning unchanged RSS transport data.

Capture received_at remains its real adapter-return timestamp. Network arrival
is separately retained; old failed receipts are never edited or replay-admitted.
"""
from datetime import datetime, timezone
from hashlib import sha256
import time
from core.strategy_account_ledger import require
from scripts.current_research_official_alert_capture import parse_official_feed, URL


class VerifiedRssTransportV3:
    def __init__(self, *, fetch, sink, clock=None, sleep=None, monotonic=None):
        self.fetch = fetch
        self.sink = sink
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep or time.sleep
        self.monotonic = monotonic or time.monotonic

    def __call__(self):
        started = self.clock()
        require(started.utcoffset() is not None, "RSS_AWARE_CLOCK")
        response = self.fetch()
        arrived = self.clock()
        require(arrived.utcoffset() is not None and arrived >= started, "RSS_CLOCK_ROLLBACK")
        raw = response["body"]
        require(type(raw) is bytes and 0 < len(raw) <= 2*1024*1024, "RSS_BODY_BUDGET")
        require(response["status"] == 200 and response.get("url", URL) == URL, "RSS_RESPONSE_INVALID")
        evidence = dict(schema="VERIFIED_RSS_TRANSPORT_TIME_V3", url=URL,
                        raw_sha256=sha256(raw).hexdigest(), stored_bytes=len(raw),
                        started_at=started.isoformat(), transport_received_at=arrived.isoformat(),
                        semantics="NETWORK_ARRIVAL_DISTINCT_FROM_CAPTURE_ADAPTER_RETURN",
                        clock_wait_requested_seconds=0.0, raw_modified=False)
        saved = False
        try:
            feed = parse_official_feed(raw, observed_at=arrived)
            require(not feed["channel"]["publication_time_issue"] and
                    all(not item["publication_time_issue"] for item in feed["items"]),
                    "RSS_PUBLICATION_TIME_INVALID")
            published = datetime.fromisoformat(feed["channel"]["published_at_utc"])
            ahead = (published-arrived).total_seconds()
            require(ahead <= 5, "RSS_PUBLICATION_TOO_FAR_AHEAD")
            evidence["channel_published_at"] = published.isoformat()
            evidence["scanned_item_count"] = len(feed["items"])
            # All original items reach the mandatory issuer-scoped notice review.
            # Future publication is neither removed nor used as historical evidence.
            evidence["future_item_indices"] = [item["index"] for item in feed["items"] if item["future_publication"]]
            evidence["future_item_semantics"] = "RETAINED_FOR_MANDATORY_ISSUER_NOTICE_REVIEW_NOT_PIT"
            wait_started = self.monotonic()
            if ahead > 0:
                evidence["clock_wait_requested_seconds"] = min(5.0, ahead+0.001)
                self.sleep(evidence["clock_wait_requested_seconds"])
            verified = self.clock()
            elapsed = self.monotonic()-wait_started
            evidence["clock_wait_elapsed_seconds"] = elapsed
            require(elapsed >= 0 and (ahead <= 0 or elapsed <= 5), "RSS_MONOTONIC_WAIT_EXCEEDED")
            require(verified.utcoffset() is not None and verified >= arrived, "RSS_CLOCK_ROLLBACK")
            require(verified >= published, "RSS_PUBLICATION_NOT_YET_OBSERVED")
            require(ahead <= 0 or (verified-arrived).total_seconds() <= 5, "RSS_CLOCK_WAIT_EXCEEDED")
            # The unchanged original consumer still scans the original complete XML.
            evidence.update(status="VERIFIED_BEFORE_CAPTURE_RETURN", verified_at=verified.isoformat())
            saved = True
            self.sink(evidence, raw)
            final = self.clock()
            require(final >= verified, "RSS_CLOCK_ROLLBACK")
            require(ahead <= 0 or (final-arrived).total_seconds() <= 5, "RSS_CLOCK_WAIT_EXCEEDED")
            final_elapsed = self.monotonic()-wait_started
            require(final_elapsed >= elapsed and (ahead <= 0 or final_elapsed <= 5), "RSS_MONOTONIC_WAIT_EXCEEDED")
            return response
        except BaseException as error:
            if not saved:
                code = error.args[0] if type(error) is ValueError and len(error.args) == 1 else None
                code = code if type(code) is str and code.startswith("RSS_") and code.replace("_", "").isalnum() else "RSS_VERIFICATION_FAILED"
                evidence.update(status="BLOCKED_BEFORE_CAPTURE_RETURN", reason=code)
                try:
                    self.sink(evidence, raw)
                except Exception:
                    pass
            raise
