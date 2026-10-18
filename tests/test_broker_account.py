from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.broker_account import (
    BrokerAccountError,
    load_broker_account,
    save_broker_account,
    validate_broker_account,
)
from unittest.mock import patch
from api.server import _broker_account_payload, _broker_safe_position


class BrokerAccountTests(unittest.TestCase):
    def _payload(self):
        return {
            "snapshot_as_of": "2026-07-31",
            "snapshot_clock": "2026-07-31T23:59:26+08:00",
            "positions": [
                {"ticker": "goog", "shares": 10, "average_cost": 350, "observed_price": 351.6},
                {"ticker": "AVGO", "shares": 6, "average_cost": 382.8, "observed_price": 386.22},
            ],
        }

    def test_round_trip_normalizes_without_strategy_fields(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "broker.json"
            save_broker_account(self._payload(), path)
            result = load_broker_account(path)
        self.assertEqual([row["ticker"] for row in result["positions"]], ["AVGO", "GOOG"])
        self.assertNotIn("H", result["positions"][0])

    def test_optional_cash_and_reported_exit_are_account_truth_only(self):
        payload = self._payload()
        payload.update({
            "snapshot_as_of": "2026-09-04",
            "deployable_cash_usd": 10615.9,
            "deployable_cash_session_date": "2026-09-03",
            "deployable_cash_persistence": "until_user_update",
            "positions_confirmed_session_date": "2026-09-03",
            "reported_closed_positions": [{
                "ticker": "NVDA", "reported_as_of": "2026-09-04", "note": "sold"
            }],
        })
        result = validate_broker_account(payload)
        self.assertEqual(result["deployable_cash_usd"], 10615.9)
        self.assertEqual(result["positions_confirmed_session_date"], "2026-09-03")
        self.assertEqual(result["deployable_cash_persistence"], "until_user_update")
        self.assertEqual(result["reported_closed_positions"][0]["ticker"], "NVDA")
        self.assertNotIn("NVDA", [row["ticker"] for row in result["positions"]])

    def test_rejects_fractional_and_duplicate_tickers(self):
        payload = self._payload()
        payload["positions"][0]["shares"] = 1.5
        with self.assertRaises(BrokerAccountError):
            validate_broker_account(payload)

    def test_rejects_unknown_cash_persistence(self):
        payload = self._payload()
        payload["deployable_cash_persistence"] = "forever_without_confirmation"
        with self.assertRaises(BrokerAccountError):
            validate_broker_account(payload)
        payload = self._payload()
        payload["positions"].append(dict(payload["positions"][0]))
        with self.assertRaises(BrokerAccountError):
            validate_broker_account(payload)

    def test_rejects_non_finite_position_and_cash_values(self):
        cases = [
            ("shares", True),
            ("shares", float("nan")),
            ("average_cost", float("nan")),
            ("average_cost", float("inf")),
            ("observed_price", float("-inf")),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                payload = self._payload()
                payload["positions"][0][field] = value
                with self.assertRaises(BrokerAccountError):
                    validate_broker_account(payload)

        for value in (True, float("nan"), float("inf"), float("-inf")):
            with self.subTest(deployable_cash_usd=value):
                payload = self._payload()
                payload["deployable_cash_usd"] = value
                with self.assertRaises(BrokerAccountError):
                    validate_broker_account(payload)

    def test_validates_snapshot_cash_and_confirmation_dates(self):
        for field in (
            "snapshot_as_of",
            "deployable_cash_session_date",
            "positions_confirmed_session_date",
        ):
            with self.subTest(field=field):
                payload = self._payload()
                payload[field] = "2026-02-30"
                with self.assertRaises(BrokerAccountError):
                    validate_broker_account(payload)

        for value in ("not-an-iso-datetime", "2026-07-31", "2026-07-31T23:59:26"):
            with self.subTest(snapshot_clock=value):
                payload = self._payload()
                payload["snapshot_clock"] = value
                with self.assertRaises(BrokerAccountError):
                    validate_broker_account(payload)

        for field in ("deployable_cash_session_date", "positions_confirmed_session_date"):
            with self.subTest(future_field=field):
                payload = self._payload()
                payload[field] = "2026-08-01"
                with self.assertRaises(BrokerAccountError):
                    validate_broker_account(payload)

    def test_positive_cash_requires_an_iso_session_date(self):
        payload = self._payload()
        payload["deployable_cash_usd"] = 100
        with self.assertRaises(BrokerAccountError):
            validate_broker_account(payload)

    def test_reported_closed_date_is_required_valid_and_not_future(self):
        for value in ("", "2026-02-30", "2026-08-01"):
            with self.subTest(reported_as_of=value):
                payload = self._payload()
                payload["reported_closed_positions"] = [{
                    "ticker": "NVDA", "reported_as_of": value,
                }]
                with self.assertRaises(BrokerAccountError):
                    validate_broker_account(payload)

    def test_server_payload_keeps_broker_only_positions_outside_strategy_prices(self):
        payload = validate_broker_account(self._payload())
        with patch("api.server.load_broker_account", return_value=payload), patch(
            "api.server._bars_for", side_effect=RuntimeError("offline")
        ):
            result = _broker_account_payload({"GOOG": 360.0})
        by_ticker = {row["ticker"]: row for row in result["positions"]}
        self.assertEqual(by_ticker["GOOG"]["price_source"], "strategy_latest_price")
        self.assertEqual(by_ticker["AVGO"]["price_source"], "broker_snapshot_observed_price")
        self.assertEqual(by_ticker["AVGO"]["shares"], 6)

    def test_safe_leg_requires_a_real_broker_position(self):
        legacy_state_shares = 129.160457
        self.assertGreater(legacy_state_shares, 0)
        self.assertIsNone(_broker_safe_position("SGOV", {"GOOG": {"shares": 10}}))
        self.assertEqual(
            _broker_safe_position("sgov", {"SGOV": {"shares": 12}}),
            {"shares": 12},
        )


if __name__ == "__main__":
    unittest.main()
