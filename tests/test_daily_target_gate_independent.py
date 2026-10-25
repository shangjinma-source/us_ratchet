# All cash fixtures are synthetic; no broker balance or transfer amount is used.
"""Independent safety boundary tests, not validation of a timing policy."""
import hashlib
import unittest
from copy import deepcopy
from data.strategy_daily_target_gate import resolve_daily_target


def fixture():
    revision = hashlib.sha256(b"immutable-ledger-fixture").hexdigest()
    args = dict(account_id="account", account_revision=revision,
                target_id="monthly-release", target_month="2026-10",
                monthly_quantities={"S": 21}, strategy_shares={"S": 14},
                available_cash="10234.56", pending_orders=[],
                now="2026-10-20T10:00:00-04:00", expected_policy_id="policy")
    signal = dict(account_id="account", account_revision=revision,
                  target_id="monthly-release", policy_id="policy",
                  evidence_id="sealed-source", observed_at="2026-10-19T20:00:00Z",
                  available_at="2026-10-19T20:01:00Z",
                  valid_from="2026-10-20T09:30:00-04:00",
                  valid_until="2026-10-20T16:00:00-04:00",
                  effective_target_quantities={"S": 14})
    return args, signal


class DailyGateIndependent(unittest.TestCase):
    def test_cash_changes_never_manufacture_signal(self):
        for cash in ("0", "10234.56", "999999999"):
            args, _ = fixture()
            args["available_cash"] = cash
            actual = resolve_daily_target(**args)
            self.assertEqual(actual["status"], "WAIT_SIGNAL")
            self.assertIsNone(actual["effective_target_quantities"])
            self.assertEqual(actual["rows"][0]["action"], "WAIT")
            self.assertFalse(actual["orders_created"])

    def test_new_york_month_and_time_boundaries(self):
        args, signal = fixture()
        args["now"] = "2026-11-01T00:30:00Z"  # October in New York.
        signal.update(valid_from="2026-10-31T20:00:00Z",
                      valid_until="2026-11-01T04:00:00Z")
        self.assertEqual(resolve_daily_target(**args, signal=signal)["status"],
                         "DAILY_TARGET_READY")
        args["now"] = "2026-11-01T04:00:00Z"
        self.assertEqual(resolve_daily_target(**args, signal=signal)["status"],
                         "WAIT_MONTHLY_TARGET")
        args, signal = fixture()
        for now, expected in ((signal["valid_from"], "DAILY_TARGET_READY"),
                              (signal["valid_until"], "WAIT_FRESH_SIGNAL"),
                              ("2026-10-20T09:29:59-04:00", "WAIT_FRESH_SIGNAL")):
            args["now"] = now
            actual = resolve_daily_target(**args, signal=signal)
            self.assertEqual(actual["status"], expected)
            if expected.startswith("WAIT"):
                self.assertIsNone(actual["effective_target_quantities"])

    def test_binding_clock_and_policy_mutations_fail_closed(self):
        args, signal = fixture()
        for key, value in (("account_id", "other"), ("account_revision", 1),
                           ("account_revision", "0" * 64), ("target_id", "other"),
                           ("policy_id", "other"), ("effective_target_quantities", {}),
                           ("available_at", "2026-10-20T21:00:00Z"),
                           ("observed_at", "2026-10-20T21:00:00Z"),
                           ("valid_from", "2026-10-20T09:30:00"),
                           ("evidence_id", "")):
            with self.subTest(key=key, value=value):
                bad = deepcopy(signal)
                bad[key] = value
                with self.assertRaises((ValueError, KeyError)):
                    resolve_daily_target(**args, signal=bad)
        for policy in (False, 1, {}, [], " "):
            bad_args = dict(args, expected_policy_id=policy)
            with self.assertRaises(ValueError):
                resolve_daily_target(**bad_args, signal=signal)

    def test_zero_cash_sell_and_pending_never_infer_fill(self):
        args, signal = fixture()
        args["available_cash"] = "0"
        signal["effective_target_quantities"] = {"S": 0}
        actual = resolve_daily_target(**args, signal=signal)
        self.assertEqual(actual["rows"][0]["action"], "SELL")
        self.assertEqual(actual["rows"][0]["held"], 14)
        self.assertFalse(actual["execution_allowed"])
        for side in ("BUY", "SELL"):
            args["pending_orders"] = [dict(account_id="account", scope="STRATEGY",
                                          security_id="S", side=side,
                                          remaining_quantity=7)]
            before = deepcopy((args, signal))
            actual = resolve_daily_target(**args, signal=signal)
            self.assertEqual(actual["rows"][0]["action"], "WAIT")
            self.assertEqual(actual["rows"][0]["held"], 14)
            self.assertEqual(actual["rows"][0]["intent"], "SELL")
            self.assertEqual((args, signal), before)
            self.assertFalse(actual["orders_created"])
            self.assertFalse(actual["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
