from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
import unittest

import test_strategy_continuous32_target_service as fixtures
from core.strategy_account_ledger import canonical


class IndependentServiceTests(unittest.TestCase):
    def test_provider_account_race_blocks_retention(self):
        with TemporaryDirectory() as folder:
            service, store, _, _ = fixtures.ContinuousServiceTests().fixture(folder)
            provider = service.provider
            def concurrent(snapshot):
                result = provider(snapshot)
                store.append(dict(kind="CASH_CONFIRM", event_id="concurrent-fixture-cash",
                                  amount="81", cash_basis="AVAILABLE_AFTER_RESERVATIONS"),
                             expected_revision=store.read()["revision"])
                return result
            service.provider = concurrent
            result = service.generate()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"], "ACCOUNT_CHANGED_DURING_TARGET")
            self.assertIsNone(service.current)

    def test_rehashed_false_profile_cannot_preview(self):
        with TemporaryDirectory() as folder:
            service, store, _, _ = fixtures.ContinuousServiceTests().fixture(folder)
            self.assertEqual(service.generate()["status"], "READY")
            before = store.path.read_bytes()
            decision, limits, state = deepcopy(service.current)
            payload = decision["payload"]
            payload["input_binding"]["continuous_iterations"] = 999
            payload["input_id"] = sha256(canonical(payload["input_binding"])).hexdigest()
            decision["decision_id"] = sha256(canonical(payload)).hexdigest()
            service.current = (decision, limits, state)
            result = service.preview()
            self.assertEqual(result["reason"], "CONTINUOUS32_PROFILE_CHANGED")
            self.assertEqual(store.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
