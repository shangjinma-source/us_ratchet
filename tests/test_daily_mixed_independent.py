from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest
import test_daily_ready_independent as fixtures
from data.strategy_daily_mixed_preview import preview_zero_cash_mixed


class MixedIndependentTests(unittest.TestCase):
    def run_case(self,c):
        return preview_zero_cash_mixed(account_store=c.store,target_store=c.monthly,
            signal_verifier=lambda *args:deepcopy(c.signal),execution_provider=c.provider.execution,
            validate_sources=c.monthly.validate_current_target_pins,policy_id="fixture-only",
            clock=lambda:c.clock[0],fee_bps="10")

    def test_sell_only_no_cap_and_no_sale_cash_reuse(self):
        with TemporaryDirectory() as directory:
            c=fixtures.IndependentReadyTests().setup_case(directory,"A",{"A":0,"B":5})
            before=c.store.path.read_bytes();target=deepcopy(c.target)
            result=self.run_case(c)
            self.assertEqual([(o["side"],o["quantity"]) for o in result["new_orders"]],[("SELL",14)])
            self.assertEqual(result["waiting_cash"][0]["quantity"],5)
            self.assertEqual(result["difference"]["new_buy_cash_required"],"0")
            self.assertEqual(result["execution_quantities"],{"A":0,"B":0})
            self.assertEqual(result["effective_target_quantities"],{"A":0,"B":5})
            self.assertFalse(c.cap_path.exists());self.assertEqual(c.store.path.read_bytes(),before)
            self.assertEqual(c.target,target)

    def test_pending_wait_and_target_race(self):
        for mode in ("pending","race"):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                c=fixtures.IndependentReadyTests().setup_case(directory,"A",{"A":0,"B":5})
                if mode=="pending":
                    c.store.append(dict(event_id="pending",kind="ORDER_OPEN",order_id="open",
                        security_id="A",side="SELL",quantity=2,limit_price="10",fee_per_share="0"),
                        expected_revision=c.store.read()["revision"])
                    c.store.append(dict(event_id="reconfirm",kind="CASH_CONFIRM",amount="0",
                        cash_basis="TOTAL_UNINVESTED"),expected_revision=c.store.read()["revision"])
                    c.signal["account_revision"]=c.store.read()["revision"]
                    def capture(**kwargs): raise AssertionError("pending cannot capture")
                    c.provider.market.capture=capture
                    result=self.run_case(c)
                    self.assertEqual(result["status"],"WAIT_PENDING_RECONCILIATION")
                    self.assertEqual(result["new_orders"],[])
                else:
                    original=c.provider.limits
                    def limits(**kwargs):
                        result=original(**kwargs)
                        c.target["payload"]["target_quantities"]["B"]=22
                        return result
                    c.provider.limits=limits
                    with self.assertRaisesRegex(ValueError,"TARGET_CHANGED"):
                        self.run_case(c)
