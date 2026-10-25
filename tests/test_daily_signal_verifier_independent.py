"""Independent clock/binding tests; synthetic releases never authorize production."""
from copy import deepcopy
import unittest
import test_strategy_daily_signal_verifier as fixtures
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle


class IndependentDailyVerifier(unittest.TestCase):
    setUp = fixtures.SignalVerifierTests.setUp
    args = fixtures.SignalVerifierTests.args

    def test_intraday_receipt_is_not_backdated_to_close_or_open(self):
        day = self.start[:10]
        self.receipt["source_received_at"] = day + "T11:00:00-05:00"
        self.receipt["available_at"] = day + "T11:02:00-05:00"
        self.receipt["valid_from"] = self.receipt["available_at"]
        args = self.args()
        args["now"] = self.receipt["available_at"]
        result = verify_daily_signal_bundle(**args)
        self.assertEqual(result["signal"]["observed_at"], self.receipt["source_received_at"])
        self.assertEqual(result["signal"]["valid_from"], self.receipt["available_at"])
        self.assertNotEqual(result["market_asof"], result["signal"]["observed_at"])
        args["now"] = self.start
        self.assertEqual(verify_daily_signal_bundle(**args)["status"], "WAIT_FRESH_SIGNAL")

    def test_future_received_and_review_before_received_rejected(self):
        day = self.start[:10]
        self.receipt["source_received_at"] = day + "T11:00:00-05:00"
        self.receipt["available_at"] = day + "T10:00:00-05:00"
        self.receipt["valid_from"] = self.receipt["available_at"]
        args = self.args()
        args["now"] = day + "T12:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "CLOCK_INVALID"):
            verify_daily_signal_bundle(**args)

    def test_unchanged_external_calendar_hash_blocks_resealed_evidence(self):
        args = self.args()
        forged = deepcopy(self.calendar)
        forged["sessions"][-2]["close"] = forged["sessions"][-2]["date"] + "T15:00:00-05:00"
        args["calendar_bytes"] = fixtures.raw(forged)
        with self.assertRaisesRegex(ValueError, "CALENDAR_HASH"):
            verify_daily_signal_bundle(**args)
        args = self.args()
        args["release_bytes"] += b" "
        with self.assertRaisesRegex(ValueError, "RELEASE_HASH"):
            verify_daily_signal_bundle(**args)

    def test_unreviewed_units_no_release_and_after_close_cannot_enable(self):
        args = self.args()
        args["trusted_release_sha256"] = None
        self.assertEqual(verify_daily_signal_bundle(**args)["status"], "WAIT_POLICY_RELEASE")
        self.receipt["normalization_reviewed"] = False
        with self.assertRaisesRegex(ValueError, "UNIT_REVIEW"):
            verify_daily_signal_bundle(**self.args())
        self.receipt["normalization_reviewed"] = True
        args = self.args()
        args["now"] = self.end
        self.assertIsNone(verify_daily_signal_bundle(**args)["signal"])


if __name__ == "__main__":
    unittest.main()
