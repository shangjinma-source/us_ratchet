import unittest
from copy import deepcopy
from data.dynamic_switch_risk_comparison import compare_with_monthly_exit


class DynamicRiskTests(unittest.TestCase):
    def arguments(self):
        days = ['2026-10-01', '2026-10-02', '2026-10-05']
        closes = {d: d+'T20:00:00+00:00' for d in days}
        histories = {}
        for sid, values in [('A', ['100', '80', '110']), ('B', ['100', '100', '100'])]:
            histories[sid] = dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                unit_asof=days[-1], currency='USD', basis_id='nominal', review_reference='fixture'),
                source_reference='fixture', closes=[dict(date=d, completed_at=closes[d], close=v) for d,v in zip(days,values)])
        return dict(account_id='fixture', prior_risk_state=None, cash='100', holdings={'A': 1},
            candidate={'A': 1, 'B': 1}, prices={'A': '110', 'B': '100'}, scenarios=[{'A': '2', 'B': '1.1'}],
            scenario_dates=[days[-1]], slippage_bps='0', history_inputs=dict(
                base_target=dict(monthly_decision_date=days[0], quantities={'A': 1, 'B': 1},
                    price_units={'A': 'nominal', 'B': 'nominal'}, origin_reference='fixture'),
                signal_date=days[-1], observed_at=days[-1]+'T21:00:00+00:00', session_dates=days,
                session_close_times=dict(closes=closes, review_reference='fixture'), histories=histories))

    def test_rebounded_candidate_stays_exited_and_both_arms_sell(self):
        arguments = self.arguments()
        original = deepcopy(arguments)
        result = compare_with_monthly_exit(**arguments)
        self.assertEqual(result['retain_targets'], {'A': 0})
        self.assertEqual(result['candidate_targets'], {'A': 0, 'B': 1})
        self.assertEqual(result['ranking'], 'SWITCH_HIGHER')
        self.assertEqual(arguments, original)
        arguments['prior_risk_state'] = result['risk_state']
        self.assertEqual(compare_with_monthly_exit(**arguments)['risk_state'], result['risk_state'])

    def test_reset_and_history_rewrite_rejected(self):
        arguments = self.arguments()
        arguments['prior_risk_state'] = compare_with_monthly_exit(**arguments)['risk_state']
        reset = deepcopy(arguments)
        reset['history_inputs']['base_target']['monthly_decision_date'] = '2026-10-02'
        with self.assertRaisesRegex(ValueError, 'CANNOT_RESET'):
            compare_with_monthly_exit(**reset)
        arguments['history_inputs']['histories']['A']['closes'][1]['close'] = '90'
        with self.assertRaisesRegex(ValueError, 'PRIOR_EXIT_HISTORY_CHANGED'):
            compare_with_monthly_exit(**arguments)

    def test_missing_history_and_coordinate_mismatch_rejected(self):
        arguments = self.arguments()
        del arguments['history_inputs']['histories']['B']
        with self.assertRaises(ValueError):
            compare_with_monthly_exit(**arguments)
        arguments = self.arguments()
        arguments['prices']['A'] = '55'
        with self.assertRaisesRegex(ValueError, 'PRICE_MISMATCH'):
            compare_with_monthly_exit(**arguments)


if __name__ == '__main__':
    unittest.main()
