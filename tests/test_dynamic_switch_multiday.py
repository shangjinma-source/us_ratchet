import unittest
from copy import deepcopy
from backtest.dynamic_switch_provider import build_dynamic_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book


class MultidayTests(unittest.TestCase):
    days = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']

    def build_inputs(self, *, decision_date, state, prior_risk_state):
        days = self.days[:self.days.index(decision_date)+1]
        values = {'A': ['100', '80', '110', '110'], 'B': ['100'] * 4}
        prices = {s: v[len(days)-1] for s,v in values.items()}
        times = {d: d+'T20:00:00+00:00' for d in days}
        histories = {s: dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
            unit_asof=decision_date, currency='USD', basis_id='fixture', review_reference='fixture'),
            source_reference='fixture', closes=[dict(date=d, completed_at=times[d], close=v) for d,v in zip(days,series)]) for s,series in values.items()}
        candidate = {'B': 2} if len(days) == 1 else {'A': 2} if len(days) == 2 else {'B': 1}
        return dict(account_id='fixture', candidate=candidate, prices=prices,
            scenarios=[{'A': '1', 'B': '2'}], scenario_dates=[decision_date], slippage_bps='0',
            history_inputs=dict(base_target=dict(monthly_decision_date=days[0], quantities={'A': 1, 'B': 1},
                price_units={'A': 'fixture', 'B': 'fixture'}, origin_reference='fixture'),
                signal_date=decision_date, observed_at=decision_date+'T21:00:00+00:00', session_dates=days,
                session_close_times=dict(closes=times, review_reference='fixture'), histories=histories))

    def test_next_open_cash_handoff_and_exit_latch(self):
        provider, audit = build_dynamic_provider(self.build_inputs)
        bars = {s: {d: dict(open=p, high=p, low=p, close=p) for d,p in zip(self.days,series)}
                for s,series in {'A': ['100','80','110','110'], 'B': ['100']*4}.items()}
        result = run_next_open_book(session_dates=self.days, ohlc=bars, initial_cash='300',
            initial_shares={'A': 1}, fee_bps='0', slippage_bps='0', order_provider=provider)
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(audit[1]['input_account']['cash'], '180')
        self.assertEqual(audit[1]['input_account']['shares'], {'A': 0, 'B': 2})
        self.assertEqual(audit[1]['signal']['comparison']['risk_state']['exited'], ['A'])
        self.assertEqual(audit[2]['signal']['comparison']['risk_state']['exited'], ['A'])
        fills = [r for r in result['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['date'],r['side'],r['quantity'],r['price']) for r in fills],
            [('2026-10-02','SELL',1,'80'),('2026-10-02','BUY',2,'100')])
        self.assertEqual(result['cash'], '180')
        self.assertEqual(result['shares'], {'A': 0, 'B': 2})

    def test_builder_cannot_override_account(self):
        def builder(**arguments):
            return dict(self.build_inputs(**arguments), cash='99999')
        provider, audit = build_dynamic_provider(builder)
        state = dict(asof=self.days[0], cash='300', shares={'A': 1})
        original = deepcopy(state)
        with self.assertRaisesRegex(ValueError, 'OVERRIDE_FORBIDDEN'):
            provider(decision_date=self.days[0], active_date=self.days[1], state=state)
        self.assertEqual(state, original)
        self.assertEqual(audit, [])

    def test_reviewed_boundary_resets_risk_without_resetting_account(self):
        self.days = ['2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03']
        def builder(**arguments):
            inputs = self.build_inputs(**arguments)
            if arguments['decision_date'] == '2026-11-02':
                history = inputs['history_inputs']
                history['base_target']['monthly_decision_date'] = '2026-11-02'
                history['session_dates'] = ['2026-11-02']
                history['session_close_times']['closes'] = {'2026-11-02': '2026-11-02T21:00:00+00:00'}
                history['observed_at'] = '2026-11-02T22:00:00+00:00'
                for series in history['histories'].values():
                    series['closes'] = [dict(series['closes'][-1], completed_at='2026-11-02T21:00:00+00:00')]
            return inputs
        bars = {s: {d: dict(open=p, high=p, low=p, close=p) for d,p in zip(self.days,series)}
                for s,series in {'A': ['100','80','110','110'], 'B': ['100']*4}.items()}
        arguments = dict(session_dates=self.days, ohlc=bars, initial_cash='300',
                         initial_shares={'A': 1}, fee_bps='0', slippage_bps='0')
        unauthorized, _ = build_dynamic_provider(builder)
        with self.assertRaisesRegex(ValueError, 'UNAUTHORIZED_DYNAMIC_RISK_RESET'):
            run_next_open_book(order_provider=unauthorized, **arguments)
        provider, audit = build_dynamic_provider(builder, authorized_risk_reset_dates=('2026-11-02',))
        result = run_next_open_book(order_provider=provider, **arguments)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(audit[1]['signal']['comparison']['risk_state']['exited'], ['A'])
        self.assertTrue(audit[2]['authorized_risk_reset_applied'])
        self.assertEqual(audit[2]['signal']['comparison']['risk_state']['exited'], [])
        self.assertEqual(audit[2]['input_account']['cash'], '180')
        self.assertEqual(audit[2]['input_account']['shares'], {'A': 0, 'B': 2})
        self.assertEqual(audit[2]['signal']['target_differences'], [])


if __name__ == '__main__':
    unittest.main()
