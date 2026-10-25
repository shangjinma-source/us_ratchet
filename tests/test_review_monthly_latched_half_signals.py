from copy import deepcopy
import unittest
import test_continuous_guided_cost_stress as fixtures
from backtest.continuous_guided_cost_stress import prepare_arm
from backtest.continuous_guided_monthly_latched_half_next_open import run_cost_monthly_latched_half_next_open
from scripts.review_monthly_latched_half_signals import review


class SignalReviewTests(unittest.TestCase):
    def setUp(self):
        self.assembled, self.bars, self.resolver = fixtures.CostStressTests().data()
        self.outcome = run_cost_monthly_latched_half_next_open(
            assembled=prepare_arm(self.assembled, 'slippage5'), ohlc=self.bars,
            history_resolver=self.resolver, initial_cash='1000', fee_bps='0', slippage_bps='5')
        self.assertEqual(self.outcome['status'], 'COMPLETE')

    def test_recomputes_real_saved_diagnostics(self):
        result = review(assembled=self.assembled, outcome=self.outcome, history_resolver=self.resolver)
        self.assertGreater(result['security_sessions'], 0)
        self.assertFalse(result['source_authenticity_certified'])

    def test_consistent_but_false_saved_mean_and_boolean_rejected(self):
        changed = deepcopy(self.outcome)
        diagnostic = changed['provider_audit'][0]['risk_overlay']['diagnostics']['A']
        diagnostic.update(sma20='999999', on=False)
        with self.assertRaisesRegex(ValueError, 'SIGNAL_DIAGNOSTIC_MISMATCH'):
            review(assembled=self.assembled, outcome=changed, history_resolver=self.resolver)

    def test_future_completion_in_supplied_history_rejected(self):
        def bad(**kwargs):
            value = deepcopy(self.resolver(**kwargs))
            value['histories']['A']['closes'][-1]['completed_at'] = '2099-01-01T16:00:00-05:00'
            return value
        with self.assertRaisesRegex(ValueError, 'SIGNAL_COMPLETION_TIME'):
            review(assembled=self.assembled, outcome=self.outcome, history_resolver=bad)

    def test_empty_unit_or_target_reference_rejected_even_when_saved_matches(self):
        for field, reason in [('unit', 'SIGNAL_UNITS'), ('origin', 'SIGNAL_TARGET_REFERENCE')]:
            with self.subTest(field=field):
                changed = deepcopy(self.outcome)
                for row in changed['provider_audit']:
                    base = row['risk_overlay']['base_target']
                    if field == 'unit':
                        base['price_units']['A'] = ''
                    else:
                        base['origin_reference'] = ''

                def bad(**kwargs):
                    value = deepcopy(self.resolver(**kwargs))
                    if field == 'unit':
                        value['base_target']['price_units']['A'] = ''
                        value['histories']['A']['units']['basis_id'] = ''
                    else:
                        value['base_target']['origin_reference'] = ''
                    return value

                with self.assertRaisesRegex(ValueError, reason):
                    review(assembled=self.assembled, outcome=changed, history_resolver=bad)

    def test_cash_only_target_still_requires_completed_session(self):
        changed = deepcopy(self.outcome)
        for row in changed['provider_audit']:
            row['monthly_ceiling'] = {}
            row['risk_overlay']['base_target'].update(quantities={}, price_units={})
            row['risk_overlay']['diagnostics'] = {}

        def bad(**kwargs):
            value = deepcopy(self.resolver(**kwargs))
            value['session_close_times']['closes'][kwargs['decision_date']] = kwargs['decision_date'] + 'T20:00:00-05:00'
            return value

        with self.assertRaisesRegex(ValueError, 'SIGNAL_CURRENT_SESSION_INCOMPLETE'):
            review(assembled=self.assembled, outcome=changed, history_resolver=bad)


if __name__ == '__main__':
    unittest.main()
