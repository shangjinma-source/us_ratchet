"""Offline clock-boundary checks: no market capture or real account writes."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import scripts.run_continuous32_upgrade as cli


class SessionClockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.calendar = self.root / cli.SESSION_CALENDAR_PATH
        self.calendar.parent.mkdir(parents=True)
        self.calendar.write_bytes((Path(__file__).resolve().parents[1] /
                                   cli.SESSION_CALENDAR_PATH).read_bytes())

    def clock(self, instant):
        return cli.regular_session_clock(self.root, lambda: datetime.fromisoformat(instant))

    def test_regular_boundaries_and_holiday(self):
        for instant in ("2026-10-20T13:29:59+00:00", "2026-10-20T20:00:00+00:00"):
            with self.assertRaisesRegex(ValueError, "OUTSIDE_REGULAR_SESSION"):
                self.clock(instant)()
        self.assertEqual(self.clock("2026-10-20T13:30:00+00:00")().hour, 13)
        with self.assertRaisesRegex(ValueError, "NO_REGULAR_SESSION"):
            self.clock("2026-11-26T16:00:00+00:00")()

    def test_half_day_and_daylight_saving(self):
        self.assertEqual(self.clock("2026-11-27T14:30:00+00:00")().hour, 14)
        self.clock("2026-11-27T17:59:59+00:00")()
        with self.assertRaisesRegex(ValueError, "OUTSIDE_REGULAR_SESSION"):
            self.clock("2026-11-27T18:00:00+00:00")()

    def test_rechecks_close_calendar_and_clock_rollback(self):
        moments = iter(map(datetime.fromisoformat, [
            "2026-10-20T19:59:59+00:00", "2026-10-20T20:00:00+00:00"]))
        checked = cli.regular_session_clock(self.root, lambda: next(moments))
        checked()
        with self.assertRaisesRegex(ValueError, "OUTSIDE_REGULAR_SESSION"):
            checked()
        moments = iter(map(datetime.fromisoformat, [
            "2026-10-20T14:01:00+00:00", "2026-10-20T14:00:00+00:00"]))
        checked = cli.regular_session_clock(self.root, lambda: next(moments))
        checked()
        with self.assertRaisesRegex(ValueError, "CLOCK_ROLLBACK"):
            checked()
        checked = self.clock("2026-10-20T14:00:00+00:00")
        checked()
        self.calendar.write_bytes(self.calendar.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "CALENDAR_CHANGED"):
            checked()

    def test_source_modes_reject_before_preparation(self):
        for execute, preflight in ((True, False), (False, True)):
            args = SimpleNamespace(root=str(self.root), execute=execute, preflight=preflight)
            with patch.object(cli, "regular_session_clock",
                              return_value=self.clock("2026-10-20T12:24:00+00:00")), \
                    patch.object(cli, "build_preparation") as prepare:
                with self.assertRaisesRegex(ValueError, "OUTSIDE_REGULAR_SESSION"):
                    cli.run(args)
                prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
