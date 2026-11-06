"""Synthetic adversarial cases; no network, private data or pytest dependency."""
import unittest
from decimal import Decimal

from scripts.research import ibm_minute_pullback_mechanism_20261106 as mechanism


def bar(minute, *, high="102.5", low="101"):
    return dict(t=minute, o=Decimal("102"), h=Decimal(high),
                l=Decimal(low), c=Decimal("102"), v=1)


class MinutePullbackIndependentTests(unittest.TestCase):
    def setUp(self):
        self.dates = ["2026-08-10", "2026-08-11", "2026-08-12",
                      "2026-08-13", "2026-08-14"]
        self.minutes = {date: [bar(minute) for minute in range(570, 960)]
                        for date in self.dates}
        self.event = dict(date=self.dates[0], entry_index=8, entry_t=578,
                          stop=Decimal("100"))

    def trade(self, mode):
        return mechanism.trade(self.minutes, self.dates, self.event, mode)

    def remove_execution_minute(self):
        del self.minutes[self.dates[0]][8]

    def test_minute_entry_cannot_skip_missing_execution_bar(self):
        self.remove_execution_minute()
        self.assertEqual(self.trade("MINUTE")["status"],
                         "UNKNOWN_MISSING_EXECUTION_MINUTE")

    def test_next_open_requires_survival_from_expected_execution_minute(self):
        self.remove_execution_minute()
        self.assertEqual(self.trade("NEXT_OPEN")["status"],
                         "UNKNOWN_SETUP_SURVIVAL_GAP")

    def test_missing_entire_holding_session_is_not_skipped(self):
        del self.minutes[self.dates[1]]
        result = self.trade("MINUTE")
        self.assertEqual(result["status"], "UNKNOWN_MISSING_HOLDING_SESSION")
        self.assertEqual(result["date"], self.dates[1])

    def test_next_open_cannot_move_to_later_available_session(self):
        del self.minutes[self.dates[1]]
        self.assertEqual(self.trade("NEXT_OPEN")["status"],
                         "UNKNOWN_MISSING_EXECUTION_SESSION")

    def test_same_bar_stop_and_target_uses_adverse_path(self):
        self.minutes[self.dates[0]][8] = bar(578, high="120", low="90")
        result = self.trade("MINUTE")
        self.assertEqual(result["status"], "OBSERVED_PRICE_ONLY")
        self.assertEqual(result["reason"], "STOP_FIRST_IF_CONFLICT")
        self.assertEqual(result["exit_date"], self.dates[0])
        self.assertEqual(result["exit_time"], 578)
        self.assertEqual(result["exit_price"], Decimal("99.9500"))
        self.assertLess(result["pnl"], 0)


if __name__ == "__main__":
    unittest.main()
