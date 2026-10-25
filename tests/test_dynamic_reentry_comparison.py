from copy import deepcopy
import unittest
from data.dynamic_switch_risk_comparison import compare_with_monthly_exit


class ReentryComparisonTests(unittest.TestCase):
    days = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08']
    prices = ['100', '80', '75', '90', '91', '72']

    def inputs(self, end):
        days = self.days[:end+1]
        times = {day: day+'T20:00:00+00:00' for day in days}
        return dict(account_id='reentry', prior_risk_state=None, cash='300', holdings={'A': 0},
                    candidate={'A': 1}, prices={'A': self.prices[end]},
                    scenarios=[{'A': '2'}], scenario_dates=[days[-1]], slippage_bps='0',
                    history_inputs=dict(
                        base_target=dict(monthly_decision_date=days[0], quantities={'A': 1},
                                         price_units={'A': 'same'}, origin_reference='fixture'),
                        signal_date=days[-1], observed_at=days[-1]+'T21:00:00+00:00', session_dates=days,
                        session_close_times=dict(closes=times, review_reference='fixture'),
                        histories={'A': dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                            unit_asof=days[-1], currency='USD', basis_id='same', review_reference='fixture'),
                            source_reference='fixture', closes=[dict(date=day, completed_at=times[day], close=price)
                                                                for day, price in zip(days, self.prices)])}))

    def entry(self):
        return dict(security_id='A', exit_date='2026-10-05', date='2026-10-07',
                    execution_id='actual-simulated-fill-1', price='92', unit_id='same')

    def test_later_signal_may_propose_but_does_not_reset_peak_or_latch(self):
        arguments = self.inputs(3)
        original = deepcopy(arguments)
        baseline = compare_with_monthly_exit(**arguments)
        self.assertEqual(baseline['candidate_targets'], {'A': 0})
        selected = compare_with_monthly_exit(**arguments, eligible_reentries={'A': '2026-10-05'})
        self.assertEqual(selected['ranking'], 'SWITCH_HIGHER')
        self.assertEqual(selected['candidate_targets'], {'A': 1})
        self.assertEqual(selected['risk_state'], baseline['risk_state'])
        self.assertEqual(selected['risk_state']['exited'], ['A'])
        self.assertEqual(selected['risk_state']['peaks'], {'A': '100'})
        self.assertEqual(arguments, original)
        with self.assertRaisesRegex(ValueError, 'LATER_CLOSE'):
            compare_with_monthly_exit(**self.inputs(2), eligible_reentries={'A': '2026-10-05'})

    def test_only_executed_entry_starts_new_peak_and_can_exit_again(self):
        prior = compare_with_monthly_exit(**self.inputs(3))['risk_state']
        bought = self.inputs(4)
        bought.update(prior_risk_state=prior, holdings={'A': 1}, cash='208')
        result = compare_with_monthly_exit(**bought, executed_reentries=[self.entry()])
        self.assertEqual(result['risk_state']['exited'], [])
        self.assertEqual(result['risk_state']['peaks'], {'A': '92'})
        later = self.inputs(5)
        later.update(prior_risk_state=result['risk_state'], holdings={'A': 1}, cash='208')
        again = compare_with_monthly_exit(**later, executed_reentries=[self.entry()])
        self.assertEqual(again['risk_state']['exited'], ['A'])
        self.assertEqual(again['retain_targets'], {'A': 0})
        unchanged = compare_with_monthly_exit(**bought)
        self.assertEqual(unchanged['risk_state']['exited'], ['A'])

    def test_future_duplicate_and_wrong_unit_fills_rejected(self):
        with self.assertRaisesRegex(ValueError, 'INVALID_EXECUTED'):
            compare_with_monthly_exit(**self.inputs(3), executed_reentries=[self.entry()])
        with self.assertRaisesRegex(ValueError, 'INVALID_EXECUTED'):
            compare_with_monthly_exit(**self.inputs(4), executed_reentries=[self.entry(), self.entry()])
        with self.assertRaisesRegex(ValueError, 'UNIT_MISMATCH'):
            compare_with_monthly_exit(**self.inputs(4), executed_reentries=[dict(self.entry(), unit_id='wrong')])


if __name__ == '__main__':
    unittest.main()
