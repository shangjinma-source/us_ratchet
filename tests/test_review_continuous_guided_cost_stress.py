from copy import deepcopy
import unittest
import test_continuous_guided_cost_stress as fixtures
from backtest.continuous_guided_cost_stress import run_cost_stress_arm
from scripts.review_continuous_guided_cost_stress import review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.assembled, self.ohlc, resolver = fixtures.CostStressTests().data()
        self.pins = {'research_contracts/test-cost.json':'a'*64}
        self.outcome = run_cost_stress_arm(arm='continuous32_half', scenario='fee1_slippage10',
            assembled=self.assembled, ohlc=self.ohlc, initial_cash='1000', history_resolver=resolver,
            reviewed_pins=self.pins)

    def check(self, outcome=None):
        return review(assembled=self.assembled, ohlc=self.ohlc, outcome=outcome or self.outcome,
            scenario='fee1_slippage10', expected_pins=self.pins, arm='continuous32_half', initial_cash='1000')

    def test_arithmetic_scope_is_explicit(self):
        result=self.check()
        self.assertEqual(result['status'],'CASH_COST_BINDINGS_VERIFIED')
        self.assertFalse(result['full_ledger_independently_replayed'])
        self.assertFalse(result['performance_validated'])

    def test_internal_cash_event_reported_as_unsupported(self):
        for event in ({'event':'CASH_DIVIDEND','cash_credited':'10'},
                      {'event':'DISTRIBUTION_APPLIED','cash_credited':'10'}):
            value=deepcopy(self.outcome);value['order_log'].append(event)
            self.assertEqual(self.check(value)['status'],'UNSUPPORTED_CASH_EVENT_REVIEW_REQUIRED')
        value=deepcopy(self.outcome)
        value['after_close_records']=[dict(date=value['daily_ledger'][0]['date'],cash='999',phase='NEW_SETTLEMENT')]
        self.assertEqual(self.check(value)['status'],'UNSUPPORTED_CASH_EVENT_REVIEW_REQUIRED')

    def test_tampered_fills_and_aggregate_rejected(self):
        for key in ('price','fee','cash_after'):
            value=deepcopy(self.outcome)
            next(r for r in value['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED')[key]='12345'
            with self.assertRaises(ValueError): self.check(value)
        value=deepcopy(self.outcome);value['fees']='12345'
        with self.assertRaises(ValueError):self.check(value)

    def test_monthly_provenance_and_cash_rejected(self):
        value=deepcopy(self.outcome)
        value['selection_account_states'][0]['source_hashes'].pop(next(iter(self.pins)))
        with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE'):self.check(value)
        value=deepcopy(self.outcome);value['selection_account_states'][0]['account_state']['cash']='999'
        with self.assertRaisesRegex(ValueError,'MONTHLY_ACTUAL_CASH'):self.check(value)

    def test_daily_cash_and_binding_rejected(self):
        value=deepcopy(self.outcome);value['daily_ledger'][0]['cash']='999'
        with self.assertRaisesRegex(ValueError,'DAILY_CASH'):self.check(value)
        value=deepcopy(self.outcome);value['cost_stress_binding']['arm']='continuous32'
        with self.assertRaisesRegex(ValueError,'ARM_BINDING'):self.check(value)


if __name__=='__main__':unittest.main()
