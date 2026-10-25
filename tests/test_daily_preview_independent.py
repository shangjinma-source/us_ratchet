"""Independent attacks on isolated orchestration using real temporary SQLite."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
import unittest
from data import strategy_daily_preview_service as module
import test_strategy_daily_preview_service as fixtures


class IndependentDailyPreview(unittest.TestCase):
    setUp = fixtures.DailyPreviewTests.setUp
    event = fixtures.DailyPreviewTests.event
    signal = fixtures.DailyPreviewTests.signal
    evidence = fixtures.DailyPreviewTests.evidence

    def test_no_signal_hold_pending_never_fetch_execution_quotes(self):
        for mode, quantity in (("missing", 21), ("expired", 21), ("valid", 14)):
            self.signal_mode, self.quantity = mode, quantity
            before = self.account.path.read_bytes()
            with patch.object(self.service, "execution_provider",
                              side_effect=AssertionError("WAIT MUST NOT QUOTE")):
                actual = self.service.preview()
            self.assertEqual(actual["new_orders"], [])
            self.assertIsNone(actual["effective_target_quantities"])
            self.assertEqual(actual["reference_quotes"], {})
            self.assertEqual(self.account.path.read_bytes(), before)
        self.signal_mode, self.quantity = "valid", 0
        self.event("ORDER_OPEN", order_id="pending", security_id="S", side="SELL",
                   quantity=2, limit_price="101", fee_per_share="0")
        before = self.account.path.read_bytes()
        with patch.object(self.service, "execution_provider",
                          side_effect=AssertionError("PENDING MUST NOT QUOTE")):
            actual = self.service.preview()
        self.assertEqual(actual["status"], "WAIT_PENDING_RECONCILIATION")
        self.assertEqual(self.account.path.read_bytes(), before)

    def test_real_difference_and_provider_share_effective_target(self):
        self.event("CASH_CONFIRM", amount="0", cash_basis="TOTAL_UNINVESTED")
        before = self.account.path.read_bytes()
        original = module.preview_scoped_account
        received = []
        def difference(**kwargs):
            received.append(deepcopy(kwargs["target_quantities"]))
            return original(**kwargs)
        with patch.object(module, "preview_scoped_account", side_effect=difference):
            actual = self.service.preview()
        self.assertEqual(received, [{"S": 7}])
        self.assertEqual(self.provider_quantity, received[0])
        self.assertEqual(actual["new_orders"][0]["side"], "SELL")
        self.assertEqual(actual["new_orders"][0]["quantity"], 7)
        self.assertEqual(self.account.path.read_bytes(), before)

    def test_signal_callback_account_race_prevents_provider(self):
        original = self.service.signal_verifier
        def racing(state, target, now):
            signal = original(state, target, now)
            self.event("CASH_CONFIRM", amount="601", cash_basis="TOTAL_UNINVESTED")
            return signal
        self.service.signal_verifier = racing
        with patch.object(self.service, "execution_provider",
                          side_effect=AssertionError("STALE ACCOUNT MUST NOT QUOTE")):
            with self.assertRaisesRegex(ValueError, "ACCOUNT_CHANGED"):
                self.service.preview()

    def test_shared_target_mutation_is_detected(self):
        self.targets.current = lambda: self.targets.target
        original = self.service.execution_provider
        def racing(state, target, now):
            result = original(state, target, now)
            self.targets.target["payload"]["target_quantities"]["S"] = 99
            return result
        self.service.execution_provider = racing
        with self.assertRaisesRegex(ValueError, "TARGET_CHANGED"):
            self.service.preview()

    def test_provider_clock_rollback_is_rejected(self):
        original = self.service.execution_provider
        def rollback(state, target, now):
            self.now -= timedelta(seconds=30)
            return original(state, target, self.now)
        self.service.execution_provider = rollback
        with self.assertRaisesRegex(ValueError, "SERVER_CLOCK_MOVED_BACKWARDS"):
            self.service.preview()

    def test_mutating_callback_target_never_reaches_difference(self):
        self.mutation = "target"
        with patch.object(module, "preview_scoped_account",
                          side_effect=AssertionError("MUTATION MUST STOP")):
            with self.assertRaisesRegex(ValueError, "MUTATED_TARGET"):
                self.service.preview()


if __name__ == "__main__":
    unittest.main()
