from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import unittest

from api.strategy_capital_transition_composition import TransitionCapitalService, SOURCES
import test_strategy_capital_service_v1 as fixtures


class CapitalTransitionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CapitalServiceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        monthly = self.fixture.service.monthly
        pins = {}
        for name in SOURCES:
            raw = (Path(__file__).resolve().parents[1] / name).read_bytes()
            path = Path(monthly.root) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        runtime, _ = monthly._for_target(monthly.current())
        self.service = TransitionCapitalService(
            monthly=monthly, validate_code=runtime.selection._pins, source_pins=pins)

    def test_original_event_remains_recoverable_without_new_selection(self):
        body = self.fixture.body
        before = self.fixture.accounts.path.read_bytes()
        self.assertEqual(self.service.record(**body)["status"], "INTENT_RECORDED")
        result = self.service.configure(event_id=body["event_id"])
        self.assertEqual(result["status"], "CONSUMED_BY_PUBLISHED_TARGET")
        with patch.object(self.service, "_current_profile", return_value="profiled"), \
             patch.object(self.fixture.provider, "selection",
                          side_effect=AssertionError("must not select")):
            self.assertEqual(self.service.status(event_id=body["event_id"]), result)
            self.assertEqual(self.service.recover_publication(event_id=body["event_id"]), result)
        self.assertFalse(self.service.profiled_journal.path.exists())
        self.assertEqual(self.fixture.accounts.path.read_bytes(), before)

    def test_same_event_in_two_journals_is_refused(self):
        body = self.fixture.body
        self.service.record(**body)
        intent = self.service.original_journal.intent(body["event_id"])
        self.service.profiled_journal.record(
            intent, account_state=self.fixture.accounts.read(),
            previous_target=self.fixture.targets.current())
        with self.assertRaisesRegex(ValueError, "CAPITAL_EVENT_EXISTS_IN_BOTH_JOURNALS"):
            self.service.status(event_id=body["event_id"])

    def test_pending_original_event_cannot_select_under_new_profile(self):
        body = self.fixture.body
        self.service.record(**body)
        with patch.object(self.service, "_current_profile", return_value="profiled"), \
             patch.object(self.fixture.provider, "selection",
                          side_effect=AssertionError("must not select")):
            with self.assertRaisesRegex(ValueError, "CAPITAL_PENDING_EVENT_REQUIRES_ORIGINAL_TARGET"):
                self.service.configure(event_id=body["event_id"])
        self.assertEqual(self.service.status(event_id=body["event_id"])["status"], "INTENT_RECORDED")


if __name__ == "__main__":
    unittest.main()
