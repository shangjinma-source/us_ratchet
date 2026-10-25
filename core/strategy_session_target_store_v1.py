"""Undeployed monthly journal with regular-session checks inside its transaction.

The original journal remains unchanged. This guards publication, not evidence
authenticity or strategy selection; callers still perform their source checks.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from scripts.register_quantity_v2_paper_protocol import safe_path


class SessionGuardedTargetStoreV1(StrategyMonthlyTargetStore):
    def __init__(self, path, *, root, calendar_path, calendar_sha256, clock=None):
        super().__init__(path)
        self.root = Path(root).resolve()
        self.calendar_path = calendar_path
        self.calendar_sha256 = calendar_sha256
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _publication_check(self, payload, previous=None):
        path = safe_path(self.root, self.calendar_path)
        with path.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024 and sha256(raw).hexdigest() == self.calendar_sha256,
                "PUBLICATION_CALENDAR_CHANGED")
        calendar = json.loads(raw)
        require(calendar["schema"] == "FIXED_EXCHANGE_SESSIONS_V1"
                and calendar["exchange"] == "NASDAQ", "PUBLICATION_CALENDAR_SCHEMA")
        now = self.clock()
        require(isinstance(now, datetime) and now.utcoffset() is not None,
                "PUBLICATION_AWARE_CLOCK_REQUIRED")
        require(previous is None or now >= previous, "PUBLICATION_CLOCK_ROLLBACK")
        day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        sessions = [row for row in calendar["sessions"] if row["date"] == day]
        require(len(sessions) == 1, "PUBLICATION_NO_SESSION")
        opening, closing = (datetime.fromisoformat(sessions[0][key]) for key in ("open", "close"))
        require(opening <= now < closing, "PUBLICATION_OUTSIDE_SESSION")
        def stamp(value):
            result = datetime.fromisoformat(value)
            require(result.utcoffset() is not None, "PUBLICATION_AWARE_TIMESTAMP_REQUIRED")
            return result
        decision = payload["decision"]
        binding = decision["payload"]["input_binding"]
        require(sha256(canonical(decision["payload"])).hexdigest() == decision["decision_id"]
                and sha256(canonical(binding)).hexdigest() == decision["payload"]["input_id"],
                "PUBLICATION_DECISION_HASH")
        require(payload["target_quantities"] == decision["payload"]["target_quantities"],
                "TARGET_QUANTITIES_MISMATCH")
        require(payload["target_month"] == day[:7], "PUBLICATION_TARGET_MONTH")
        valuation = stamp(binding["valuation_at"])
        created = stamp(payload["created_at"])
        require(opening <= valuation <= created <= now < closing, "PUBLICATION_VALUATION_SESSION")
        require(binding["valuation_date"] == day, "PUBLICATION_VALUATION_DATE")
        marks = binding["marks"]
        require(isinstance(marks, dict) and bool(marks), "PUBLICATION_MARKS_REQUIRED")
        for mark in marks.values():
            observed = stamp(mark["observed_at"])
            captured = stamp(mark["captured_at"])
            require(opening <= observed <= valuation and opening <= captured <= valuation,
                    "PUBLICATION_MARK_SESSION")
            require((now-observed).total_seconds() < 900
                    and (now-captured).total_seconds() < 900, "PUBLICATION_MARK_STALE")
        return now

    def append(self, payload):
        payload = deepcopy(payload)
        item = dict(target_id=sha256(canonical(payload)).hexdigest(), payload=payload)
        raw = canonical(item).decode()
        require(len(raw.encode()) <= 8*1024*1024, "TARGET_TOO_LARGE")
        # Existing identical operations are reads, including after close. No
        # initialization or write transaction is needed for this common retry.
        old = self.operation(payload["request"]["event_id"])
        if old is not None:
            require(old == item, "TARGET_EVENT_CONFLICT")
            return old
        checked = self._publication_check(payload)
        with closing(self._connect(True)) as con:
            try:
                # In rollback-journal mode EXCLUSIVE also waits for readers.
                # Move that wait before the session check, not into COMMIT.
                # In WAL mode readers do not block this writer's commit.
                con.execute("BEGIN EXCLUSIVE")
                rows = self._rows(con)
                for old in rows:
                    if old["payload"]["request"]["event_id"] == payload["request"]["event_id"]:
                        require(old == item, "TARGET_EVENT_CONFLICT")
                        con.rollback()
                        return old
                # Lock waits may cross the close: check only after acquiring it.
                checked = self._publication_check(payload, checked)
                require(payload["previous_target_id"] == (rows[-1]["target_id"] if rows else None),
                        "STALE_TARGET")
                require(not rows or payload["account_id"] == rows[-1]["payload"]["account_id"],
                        "TARGET_ACCOUNT_CHANGED")
                require(len(rows) < 1000 and sum(len(canonical(row)) for row in rows)
                        + len(raw.encode()) <= 64*1024*1024, "TARGET_HISTORY_BUDGET")
                checked = self._publication_check(payload, checked)
                con.execute("INSERT INTO targets VALUES(?,?,?)",
                            (len(rows)+1, payload["request"]["event_id"], raw))
                self._publication_check(payload, checked)
                con.commit()
                return item
            except BaseException:
                con.rollback()
                raise
