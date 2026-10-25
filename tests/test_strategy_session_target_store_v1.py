from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from core.strategy_session_target_store_v1 import SessionGuardedTargetStoreV1

CALENDAR = "research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json"


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        raw = (Path(__file__).resolve().parents[1]/CALENDAR).read_bytes()
        self.calendar = self.root/CALENDAR
        self.calendar.parent.mkdir(parents=True)
        self.calendar.write_bytes(raw)
        self.now = datetime.fromisoformat("2026-10-20T19:59:30+00:00")
        self.store = SessionGuardedTargetStoreV1(
            self.root/"targets.sqlite3", root=self.root, calendar_path=CALENDAR,
            calendar_sha256=sha256(raw).hexdigest(), clock=lambda: self.now)

    def payload(self, at="2026-10-20T19:59:00+00:00"):
        binding = dict(valuation_at=at, valuation_date=at[:10],
                       marks={"A": dict(observed_at=at, captured_at=at)})
        decision = dict(input_binding=binding, input_id=sha256(canonical(binding)).hexdigest(),
                        target_quantities={"A": 1})
        return dict(schema="REAL_STRATEGY_MONTHLY_TARGET_V1", account_id="fixture",
                    target_month=at[:7], previous_target_id=None, created_at=at,
                    request=dict(event_id="fixture-event"),
                    decision=dict(payload=decision, decision_id=sha256(canonical(decision)).hexdigest()),
                    target_quantities={"A": 1})

    def test_identical_after_close_is_read_only_and_conflict_is_not_retry(self):
        payload = self.payload()
        saved = self.store.append(payload)
        before = self.store.path.read_bytes()
        self.now = datetime.fromisoformat("2026-10-20T20:01:00+00:00")
        with patch.object(self.store, "_publication_check", side_effect=AssertionError("not a publication")):
            self.assertEqual(self.store.append(payload), saved)
        self.assertEqual(self.store.path.read_bytes(), before)
        changed = deepcopy(payload)
        changed["created_at"] = "2026-10-20T19:59:01+00:00"
        with self.assertRaisesRegex(ValueError, "EVENT_CONFLICT"):
            self.store.append(changed)
        self.assertEqual(self.store.current(), saved)

    def test_real_sqlite_lock_wait_crosses_close_and_rolls_back(self):
        self.store._initialize()
        con = sqlite3.connect(self.store.path, isolation_level=None)
        self.addCleanup(con.close)
        con.execute("BEGIN IMMEDIATE")
        reached = threading.Event()
        original = self.store._connect
        def connection(write=False):
            if write:
                reached.set()
            return original(write)
        errors = []
        def append():
            try:
                self.store.append(self.payload())
            except Exception as error:
                errors.append(error)
        with patch.object(self.store, "_connect", side_effect=connection):
            worker = threading.Thread(target=append)
            worker.start()
            self.assertTrue(reached.wait(3))
            self.now = datetime.fromisoformat("2026-10-20T20:00:01+00:00")
            con.rollback()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("PUBLICATION_OUTSIDE_SESSION", str(errors[0]))
        self.assertEqual(self.store.history(), [])

    def test_commit_boundary_rolls_back_insert(self):
        moments = iter(map(datetime.fromisoformat, [
            "2026-10-20T19:59:59+00:00"]*3 + ["2026-10-20T20:00:00+00:00"]))
        self.store.clock = lambda: next(moments)
        with self.assertRaisesRegex(ValueError, "OUTSIDE_SESSION"):
            self.store.append(self.payload())
        self.assertEqual(self.store.history(), [])

    def test_real_reader_lock_wait_is_before_session_check(self):
        self.store._initialize()
        reader = sqlite3.connect(self.store.path, isolation_level=None)
        self.addCleanup(reader.close)
        self.assertEqual(reader.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM targets").fetchall()
        reached = threading.Event()
        original = self.store._connect
        def connection(write=False):
            if write:
                reached.set()
            return original(write)
        errors = []
        def append():
            try:
                self.store.append(self.payload())
            except Exception as error:
                errors.append(error)
        with patch.object(self.store, "_connect", side_effect=connection):
            worker = threading.Thread(target=append)
            worker.start()
            self.assertTrue(reached.wait(3))
            # Let an IMMEDIATE implementation reach (and wait in) COMMIT.
            # EXCLUSIVE must instead remain blocked before its first locked check.
            worker.join(0.1)
            self.assertTrue(worker.is_alive())
            self.now = datetime.fromisoformat("2026-10-20T20:00:01+00:00")
            reader.rollback()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("PUBLICATION_OUTSIDE_SESSION", str(errors[0]))
        self.assertEqual(self.store.history(), [])

    def test_half_day_and_prepared_previous_session_refused(self):
        self.now = datetime.fromisoformat("2026-11-27T18:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "OUTSIDE_SESSION"):
            self.store.append(self.payload("2026-11-27T17:59:00+00:00"))
        self.assertFalse(self.store.path.exists())
        self.now = datetime.fromisoformat("2026-10-21T13:30:10+00:00")
        with self.assertRaisesRegex(ValueError, "VALUATION_SESSION"):
            self.store.append(self.payload())
        self.assertFalse(self.store.path.exists())

    def test_stale_marks_and_calendar_tamper(self):
        self.now = datetime.fromisoformat("2026-10-20T19:59:00+00:00")
        with self.assertRaisesRegex(ValueError, "MARK_STALE"):
            self.store.append(self.payload("2026-10-20T19:44:00+00:00"))
        self.calendar.write_bytes(self.calendar.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError, "CALENDAR_CHANGED"):
            self.store.append(self.payload())


if __name__ == "__main__":
    unittest.main()
