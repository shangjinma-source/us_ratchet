from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.broker_account import (
    BrokerAccountError, broker_account_fingerprint, load_broker_account,
    save_broker_account, update_broker_position, validate_broker_account,
)
from api.server import api_update_broker_position


class BrokerPositionEntryTests(unittest.TestCase):
    def setUp(self):
        self.account = validate_broker_account({
            "snapshot_as_of": "2026-09-04", "snapshot_clock": "2026-09-04T02:18:23+08:00",
            "positions_confirmed_session_date": "2026-09-03",
            "deployable_cash_usd": 20000, "deployable_cash_session_date": "2026-09-03",
            "deployable_cash_persistence": "until_user_update",
            "positions": [{"ticker": "MU", "shares": 3, "average_cost": 883.6,
                           "observed_price": 830.2},
                          {"ticker": "TSM", "shares": 2, "average_cost": 428.62,
                           "observed_price": 406.19}],
        })
        self.clock = datetime.fromisoformat("2026-10-13T12:00:00+08:00")

    def test_absolute_edit_preserves_cash_other_positions_and_confirmation(self):
        before = deepcopy(self.account)
        updated, difference = update_broker_position(
            before, {"ticker": "mu", "shares": 1}, clock=self.clock)
        self.assertEqual(self.account, before)
        self.assertEqual(difference["old_shares"], 3)
        self.assertEqual(updated["positions"][0]["shares"], 1)
        self.assertEqual(updated["positions"][0]["average_cost"], 883.6)
        self.assertEqual(updated["positions"][1], before["positions"][1])
        for field in ("deployable_cash_usd", "deployable_cash_session_date",
                      "positions_confirmed_session_date"):
            self.assertEqual(updated[field], before[field])

    def test_explicit_closure_all_cash_account_and_duplicate_are_supported(self):
        updated, _ = update_broker_position(self.account, {"ticker": "MU", "shares": 0}, clock=self.clock)
        duplicate, _ = update_broker_position(updated, {"ticker": "MU", "shares": 0}, clock=self.clock)
        self.assertEqual(updated, duplicate)
        empty, _ = update_broker_position(updated, {"ticker": "TSM", "shares": 0}, clock=self.clock)
        self.assertEqual(empty["positions"], [])
        self.assertEqual(empty["deployable_cash_usd"], 20000)
        self.assertEqual(len(empty["reported_closed_positions"]), 2)

    def test_rejects_invalid_without_mutation_and_new_position_needs_cost(self):
        for body in ({"ticker": "MU", "shares": True}, {"ticker": "MU", "shares": 1.5},
                     {"ticker": "MU", "shares": -1}, {"ticker": "MU", "shares": float("nan")},
                     {"ticker": "../MU", "shares": 1}, {"ticker": "NEW", "shares": 2},
                     {"ticker": "NEW", "shares": 0}):
            with self.subTest(body=body), self.assertRaises(BrokerAccountError):
                update_broker_position(self.account, body, clock=self.clock)
        new, _ = update_broker_position(self.account, {"ticker": "NEW", "shares": 2, "average_cost": 50}, clock=self.clock)
        self.assertEqual(next(row for row in new["positions"] if row["ticker"] == "NEW")["average_cost"], 50)

    def test_temp_api_preview_save_backup_conflict_and_no_strategy_write(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            save_broker_account(self.account, path)
            original = path.read_bytes()
            body = {"ticker": "MU", "shares": 0,
                    "account_fingerprint": broker_account_fingerprint(self.account)}
            with patch("api.server.BROKER_ACCOUNT_PATH", path), patch("api.server.audit_log") as audit, \
                    patch("api.server.load_portfolio", side_effect=AssertionError("strategy read")), \
                    patch("api.server.save_portfolio", side_effect=AssertionError("strategy write")):
                preview = api_update_broker_position({**body, "preview": True})
                self.assertTrue(preview["preview"])
                self.assertEqual(path.read_bytes(), original)
                self.assertFalse(path.with_suffix(".json.bak").exists())
                result = api_update_broker_position(body)
                self.assertFalse(result["preview"])
                self.assertEqual(path.with_suffix(".json.bak").read_bytes(), original)
                saved = path.read_bytes()
                stale = api_update_broker_position(body)
                self.assertEqual(stale.status_code, 409)
                self.assertEqual(path.read_bytes(), saved)
                duplicate = api_update_broker_position({**body, "account_fingerprint": result["account_fingerprint"]})
                self.assertTrue(duplicate["unchanged"])
                self.assertEqual(audit.call_count, 1)
                self.assertEqual(load_broker_account(path)["deployable_cash_usd"], 20000)


if __name__ == "__main__":
    unittest.main()
