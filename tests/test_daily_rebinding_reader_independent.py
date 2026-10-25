from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch
import test_strategy_daily_rebinding_reader as fixtures


class IndependentReaderTests(unittest.TestCase):
    def fixture(self, bound=True):
        helper=fixtures.ReaderTests()
        result=helper.fixture(bound)
        self.addCleanup(helper.doCleanups)
        return result

    def test_actual_half_21_is_10_and_sell_then_cash_does_not_change_ceiling(self):
        case,reader,parent=self.fixture()
        case.event("DIRECT_FILL",security_id="A",side="BUY",quantity=14,price="100",fees="0",
                   executed_at=case.clock.isoformat())
        target=case.targets.current()
        first=reader(case.accounts.read(),target,case.clock)
        self.assertEqual(first["signal"]["effective_target_quantities"],{"A":10})
        case.event("DIRECT_FILL",security_id="A",side="SELL",quantity=4,price="100",fees="0",
                   executed_at=case.clock.isoformat())
        case.event("CASH_CONFIRM",amount="400",cash_basis="TOTAL_UNINVESTED")
        before=(case.accounts.path.read_bytes(),case.targets.path.read_bytes())
        second=reader(case.accounts.read(),target,case.clock)
        self.assertEqual(second["signal"]["effective_target_quantities"],{"A":10})
        self.assertEqual(case.accounts.read()["shares"],{"A":10})
        self.assertEqual(second["source_received_at"],parent["source_received_at"])
        self.assertEqual(before,(case.accounts.path.read_bytes(),case.targets.path.read_bytes()))

    def test_no_release_does_not_read_and_unbound_parent_cannot_promote(self):
        case,reader,_=self.fixture(False)
        with self.assertRaisesRegex(ValueError,"REVIEWED_PARENT_POLICY_BINDING_REQUIRED"):
            reader(case.accounts.read(),case.targets.current(),case.clock)
        reader.release_sha=None
        with patch.object(reader.producer,"prepare",side_effect=AssertionError("must not read")):
            self.assertEqual(reader(case.accounts.read(),case.targets.current(),case.clock)["status"],
                             "WAIT_POLICY_RELEASE")

    def test_full_verifier_authenticates_release_bytes_after_rebind(self):
        case,reader,_=self.fixture()
        path=Path(case.temp.name)/"release.json"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"RELEASE_HASH_MISMATCH"):
            reader(case.accounts.read(),case.targets.current(),case.clock)
