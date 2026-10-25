import unittest
from copy import deepcopy

from backtest.dynamic_risk_units import migrate_risk_splits, reviewed_split_schedule
from backtest.dynamic_switch_provider import build_dynamic_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book


class DynamicSplitTests(unittest.TestCase):
    def event(self):
        return dict(event_id='split-A', type='split', date='2026-10-02', security_id='A',
                    new_shares='2', old_shares='1', old_unit_id='old', new_unit_id='new',
                    source_references=['reviewed-fixture'])

    def test_split_preserves_equity_then_real_twenty_percent_drop_exits(self):
        days = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']
        nominal = ['100', '50', '40', '40']

        def builder(*, decision_date, state, prior_risk_state):
            end = days.index(decision_date)
            history_days = days[:end+1]
            values = ['100'] if end == 0 else ['50', '50', '40'][:end+1]
            unit = 'old' if end == 0 else 'new'
            times = {day: day+'T20:00:00+00:00' for day in history_days}
            return dict(account_id='split-test', candidate={}, prices={'A': nominal[end]},
                        scenarios=[{'A': '1'}], scenario_dates=[decision_date], slippage_bps='0',
                        history_inputs=dict(
                            base_target=dict(monthly_decision_date=days[0], quantities={'A': 1},
                                             price_units={'A': unit}, origin_reference='fixture'),
                            signal_date=decision_date, observed_at=decision_date+'T21:00:00+00:00',
                            session_dates=history_days,
                            session_close_times=dict(closes=times, review_reference='fixture'),
                            histories={'A': dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                                unit_asof=decision_date, currency='USD', basis_id=unit, review_reference='fixture'),
                                source_reference='fixture', closes=[dict(date=day, completed_at=times[day], close=value)
                                                                    for day, value in zip(history_days, values)])}))

        event = self.event()
        provider, audit = build_dynamic_provider(builder, reviewed_risk_splits=[event])
        bars = {'A': {day: dict(open=value, high=value, low=value, close=value) for day, value in zip(days, nominal)}}
        result = run_next_open_book(session_dates=days, ohlc=bars, initial_cash='300',
                                   initial_shares={'A': 1}, fee_bps='0', slippage_bps='0',
                                   events=[event], order_provider=provider)
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(audit[1]['input_account']['shares']['A'], 2)
        self.assertEqual(audit[1]['signal']['comparison']['risk_state']['peaks']['A'], '50')
        self.assertEqual(audit[1]['signal']['comparison']['risk_state']['exited'], [])
        self.assertEqual(audit[1]['risk_unit_events_applied'], ['split-A'])
        self.assertEqual(audit[2]['risk_unit_events_applied'], [])
        self.assertEqual(audit[2]['signal']['comparison']['risk_state']['exited'], ['A'])
        fills = [row for row in result['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(row['date'], row['side'], row['quantity'], row['price']) for row in fills],
                         [('2026-10-06', 'SELL', 2, '40')])
        self.assertEqual(result['cash'], '380')

    def test_migration_keeps_exit_latch_and_rejects_wrong_units(self):
        state = dict(session_date='2026-10-01', decision_date='2026-10-01',
                     peaks={'A': '100'}, last_closes={'A': '80'}, unit_ids={'A': 'old'}, exited=['A'])
        original = deepcopy(state)
        events = reviewed_split_schedule([self.event()])
        future, applied = migrate_risk_splits(state, through_date='2026-10-01', events=events)
        self.assertEqual(future, original)
        self.assertEqual(applied, [])
        updated, applied = migrate_risk_splits(state, through_date='2026-10-02', events=events)
        self.assertEqual(updated['exited'], ['A'])
        self.assertEqual(updated['last_closes'], {'A': '40'})
        self.assertEqual(state, original)
        with self.assertRaisesRegex(ValueError, 'PRIOR_UNIT_MISMATCH'):
            migrate_risk_splits(updated, through_date='2026-10-02', events=events)
        with self.assertRaisesRegex(ValueError, 'UNIQUE_RISK_EVENT'):
            reviewed_split_schedule([self.event(), self.event()])

    def test_identity_conversion_continues_book_without_old_security_prices(self):
        from fractions import Fraction
        import test_dynamic_switch_multiday as fixtures
        fixture = fixtures.MultidayTests()
        days = fixture.days

        def builder(**arguments):
            inputs = fixture.build_inputs(**arguments)
            if arguments['decision_date'] == days[0]:
                return inputs
            inputs['prices']['C'] = str(Fraction(inputs['prices'].pop('A')) / 2)
            if 'A' in inputs['candidate']:
                inputs['candidate']['C'] = inputs['candidate'].pop('A') * 2
            for scenario in inputs['scenarios']:
                scenario['C'] = scenario.pop('A')
            history = inputs['history_inputs']
            target = history['base_target']
            target['quantities']['C'] = target['quantities'].pop('A')
            target['price_units'].pop('A')
            target['price_units']['C'] = 'successor-unit'
            series = history['histories'].pop('A')
            series['units']['basis_id'] = 'successor-unit'
            for row in series['closes']:
                row['close'] = str(Fraction(row['close']) / 2)
            history['histories']['C'] = series
            return inputs

        event = dict(self.event(), type='split_identity', new_security_id='C',
                     old_unit_id='fixture', new_unit_id='successor-unit')
        provider, audit = build_dynamic_provider(builder, reviewed_risk_splits=[event])
        series = {'A': {days[0]: '100'}, 'C': dict(zip(days[1:], ['40', '55', '55'])),
                  'B': {day: '100' for day in days}}
        bars = {sid: {day: dict(open=value, high=value, low=value, close=value)
                      for day, value in values.items()} for sid, values in series.items()}
        result = run_next_open_book(session_dates=days, ohlc=bars, initial_cash='300',
                                   initial_shares={'A': 1}, fee_bps='0', slippage_bps='0',
                                   events=[event], order_provider=provider)
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(result['cash'], '180')
        self.assertEqual(audit[1]['input_account']['shares']['A'], 0)
        self.assertEqual(audit[1]['risk_unit_events_applied'], ['split-A'])
        self.assertEqual(audit[1]['signal']['comparison']['risk_state']['exited'], ['C'])
        self.assertEqual(audit[2]['signal']['comparison']['risk_state']['exited'], ['C'])

    def test_conversion_cannot_merge_two_risk_histories_or_unlock_exit(self):
        state = dict(session_date='2026-10-01', decision_date='2026-10-01',
                     peaks={'A': '100'}, last_closes={'A': '80'}, unit_ids={'A': 'old'}, exited=['A'])
        event = dict(self.event(), type='ads_conversion', new_security_id='C',
                     new_shares='1', old_shares='2')
        events = reviewed_split_schedule([event])
        result, _ = migrate_risk_splits(state, through_date='2026-10-02', events=events)
        self.assertEqual(result['peaks'], {'C': '200'})
        self.assertEqual(result['exited'], ['C'])
        state['peaks']['C'] = '300'
        with self.assertRaisesRegex(ValueError, 'SUCCESSOR_HISTORY_COLLISION'):
            migrate_risk_splits(state, through_date='2026-10-02', events=events)


if __name__ == '__main__':
    unittest.main()
