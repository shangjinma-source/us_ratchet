import unittest
from copy import deepcopy
from test_current_quantity_v2_risk_overlays import fixture
from backtest.current_quantity_v2_signal_history import build_signal_history_resolver
from backtest.current_quantity_v2_risk_overlays import sma20_target


class SignalHistoryTests(unittest.TestCase):
    def inputs(self):
        args = fixture({'A': [100] * 21})
        day = args['signal_date']
        snapshots = {day: dict(observed_at=args['observed_at'],
            review_reference='synthetic-reviewed-snapshot', histories=args['histories'])}
        inputs = dict(session_dates=args['session_dates'],
                      session_close_times=args['session_close_times'], snapshots=snapshots)
        call = dict(decision_date=day, target_quantities={'A': 7},
                    monthly_decision_date=day, count=20)
        return inputs, call

    def test_exact_window_and_frozen_input_future_isolation(self):
        inputs, call = self.inputs()
        day = call['decision_date']
        inputs['snapshots'][day]['histories']['A']['closes'].append(
            dict(date='2099-01-01', completed_at='invalid-future', close='invalid'))
        resolve = build_signal_history_resolver(**inputs)
        result = resolve(**call)
        self.assertEqual(len(result['histories']['A']['closes']), 20)
        self.assertEqual(sma20_target(signal_date=day, **result)['target_quantities'], {'A': 0})
        inputs['snapshots'][day]['histories']['A']['closes'][-2]['close'] = '999'
        self.assertEqual(result, resolve(**call))

    def test_missing_and_duplicate_past_dates_fail(self):
        inputs, call = self.inputs()
        original = deepcopy(inputs)
        rows = inputs['snapshots'][call['decision_date']]['histories']['A']['closes']
        rows.pop(5)
        with self.assertRaises(KeyError):build_signal_history_resolver(**inputs)(**call)
        inputs = original
        rows = inputs['snapshots'][call['decision_date']]['histories']['A']['closes']
        rows.append(deepcopy(rows[5]))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_HISTORY_DATE'):
            build_signal_history_resolver(**inputs)(**call)

    def test_empty_target_requires_only_current_close_schedule(self):
        inputs, call = self.inputs()
        day = call['decision_date']
        inputs['session_close_times']['closes'] = {day: inputs['session_close_times']['closes'][day]}
        inputs['snapshots'][day]['histories'] = {}
        call['target_quantities'] = {}
        result = build_signal_history_resolver(**inputs)(**call)
        self.assertEqual(sma20_target(signal_date=day, **result)['target_quantities'], {})


if __name__ == '__main__':
    unittest.main()
