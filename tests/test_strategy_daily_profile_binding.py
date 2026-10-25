from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_continuous32_target_decision import decide_target, PROFILE_ID, VERSION
from data.strategy_daily_profile_binding import validate_daily_profile_binding
import test_strategy_continuous32_target_decision as fixtures


class DailyProfileBindingTests(unittest.TestCase):
    def fixture(self, folder):
        decision = decide_target(**fixtures.ContinuousTargetTests().arguments(folder))
        binding = decision["payload"]["input_binding"]
        payload = dict(schema="REAL_STRATEGY_MONTHLY_TARGET_V1", decision=decision,
                       account_id=binding["account_id"], target_month="2026-01",
                       created_at="2026-01-02T15:00:00+00:00",
                       previous_target_id=None, runtime_pins={},
                       request=dict(event_id="isolated-profile-check", reason="INITIAL",
                                    expected_revision=binding["account_revision"],
                                    previous_target_id=None),
                       target_quantities=deepcopy(decision["payload"]["target_quantities"]))
        target = {"payload": payload, "target_id": sha256(canonical(payload)).hexdigest()}
        release = dict(schema="SERVER_DAILY_POLICY_RELEASE_V1", approved=True,
                       selector_profile=PROFILE_ID, selection_method=VERSION,
                       continuous_iterations=32)
        return target, release

    def check(self, target, release):
        raw = canonical(release)
        return validate_daily_profile_binding(release_bytes=raw,
            trusted_release_sha256=sha256(raw).hexdigest(), target=target)

    def rehash(self, target):
        decision = target["payload"]["decision"]
        payload = decision["payload"]
        payload["input_id"] = sha256(canonical(payload["input_binding"])).hexdigest()
        decision["decision_id"] = sha256(canonical(payload)).hexdigest()
        target["target_id"] = sha256(canonical(target["payload"])).hexdigest()

    def test_real_tiny_selection_and_self_consistent_profile_tampering(self):
        with TemporaryDirectory() as folder:
            target, release = self.fixture(folder)
            original = deepcopy(target)
            self.assertEqual(self.check(target, release)["target_id"], target["target_id"])
            self.assertEqual(target, original)
            for field, value in (("selector_profile", "ORIGINAL_V2"),
                                 ("selection_method", "ORIGINAL_V2"),
                                 ("continuous_iterations", 31)):
                bad = deepcopy(target)
                bad["payload"]["decision"]["payload"]["input_binding"][field] = value
                self.rehash(bad)
                with self.subTest(field=field), self.assertRaisesRegex(
                        ValueError, "DAILY_TARGET_SELECTOR_PROFILE_MISMATCH"):
                    self.check(bad, release)
            bad = deepcopy(target)
            bad["payload"]["decision"]["payload"]["target_quantities"] = {"A": 999999}
            bad["payload"]["target_quantities"] = {"A": 999999}
            self.rehash(bad)
            with self.assertRaisesRegex(ValueError, "DAILY_PROFILE_TARGET_QUANTITIES_MISMATCH"):
                self.check(bad, release)
            for field, value, error in (
                    ("account_id", "another-account", "DAILY_PROFILE_ACCOUNT_MISMATCH"),
                    ("target_quantities", {"A": 999999}, "DAILY_PROFILE_PUBLISHED_QUANTITIES_MISMATCH")):
                bad = deepcopy(target)
                bad["payload"][field] = value
                self.rehash(bad)
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                    self.check(bad, release)

    def test_unapproved_release_and_duplicate_fields_rejected(self):
        with TemporaryDirectory() as folder:
            target, release = self.fixture(folder)
            with self.assertRaisesRegex(ValueError, "PROFILE_RELEASE_NOT_APPROVED"):
                self.check(target, dict(release, approved=False))
            raw = b'{"approved":true,"approved":false}'
            with self.assertRaisesRegex(ValueError, "PROFILE_RELEASE_DUPLICATE_FIELD"):
                validate_daily_profile_binding(release_bytes=raw,
                    trusted_release_sha256=sha256(raw).hexdigest(), target=target)


if __name__ == "__main__":
    unittest.main()
