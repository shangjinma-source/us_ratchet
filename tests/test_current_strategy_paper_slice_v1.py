import unittest
from copy import deepcopy
from fractions import Fraction

from test_current_quantity_v2_risk_overlays import fixture
from backtest.current_strategy_paper_slice_v1 import (
    SCOPE, MODEL, create_book, preview, transact, project, replay)


def book(fees='0'):
    return create_book(dict(schema='CURRENT_STRATEGY_PAPER_FIXTURE_APPLICATION_V1',
        scope=SCOPE, account_id='paper-fixture:test', initial_cash='20000',
        fee_bps=fees, model=MODEL, activation=False))


def proposal(state, quantities=None, on=True, day='2026-02-02', prices=None):
    quantities = quantities or {'A': 10}
    prices = prices or {sid: '100' for sid in set(quantities) | set(state['shares'])}
    args = fixture({sid: [100]*19+[101 if on else 100] for sid in quantities}, quantities)
    now = day+'T10:00:10-05:00'
    quotes = {sid: dict(mark=price, buy=price, sell=price, observed_at=now,
                       valid_until=day+'T10:01:00-05:00') for sid, price in prices.items()}
    return preview(state, daily_inputs=args, quotes=quotes, now=now,
                   session_close=day+'T16:00:00-05:00')


def accept(state, p, identifier='accept'):
    return transact(state, dict(kind='ACCEPT', operation_id=identifier,
        expected_revision=state['revision'], proposal=p, accepted_at=p['inputs']['now']))


def bar(sid='A', day='2026-02-02', minute='10:01', low='99', high='101'):
    end = minute[:3] + str(int(minute[3:])+1).zfill(2)
    return dict(security_id=sid, start=day+'T'+minute+':00-05:00',
                end=day+'T'+end+':00-05:00', open='100', close='100', low=low, high=high)


def settle(state, identifier='settle', day='2026-02-02', rows=None):
    minutes = {oid: [bar(order['security_id'], day)] for oid, order in state['orders'].items()
               if order['closed'] is None} if rows is None else rows
    return transact(state, dict(kind='SETTLE', operation_id=identifier,
        expected_revision=state['revision'], minutes=minutes,
        observed_through=day+'T10:02:00-05:00', evaluated_at=day+'T10:02:01-05:00'))


class CurrentStrategyPaperSliceTests(unittest.TestCase):
    def test_buy_fill_exact_cash_and_next_hold_without_real_events(self):
        state = book('10'); original = deepcopy(state)
        p = proposal(state)
        self.assertEqual(state, original)
        self.assertEqual(p['difference']['new_orders'][0]['quantity'], 10)
        state = settle(accept(state, p))
        self.assertEqual(state['cash'], '18999')
        self.assertEqual(state['shares'], {'A': 10})
        self.assertEqual(project(state)['schema'], 'PAPER_DECISION_PROJECTION_V1')
        self.assertEqual(proposal(state, day='2026-02-03')['difference']['new_orders'], [])
        self.assertEqual(replay(state), state)
        self.assertFalse(state['real_account'])
        self.assertFalse(state['selector_verified'])

    def test_half_monthly_not_half_held_and_recovery(self):
        state = book()
        state = settle(accept(state, proposal(state, {'A': 14})))
        p = proposal(state, {'A': 13}, on=False, day='2026-02-03')
        self.assertEqual(p['monthly'], {'A': 13})
        self.assertEqual(p['effective'], {'A': 6})
        self.assertEqual(p['difference']['new_orders'][0]['side'], 'SELL')
        self.assertEqual(p['difference']['new_orders'][0]['quantity'], 8)
        pending = accept(state, p, 'sell')
        conflict = proposal(pending, {'A': 13}, day='2026-02-03')
        self.assertTrue(conflict['difference']['cancel_before_recalculate'])
        state = settle(pending, 'sell-fill', '2026-02-03')
        p = proposal(state, {'A': 13}, day='2026-02-04')
        self.assertEqual(p['difference']['new_orders'][0]['quantity'], 7)

    def test_expired_quote_cannot_accept_but_does_not_cancel_day_order(self):
        state = book(); p = proposal(state)
        with self.assertRaisesRegex(ValueError, 'PAPER_ACCEPT_OUTSIDE_1000'):
            transact(state, dict(kind='ACCEPT', operation_id='late', expected_revision=state['revision'],
                proposal=p, accepted_at='2026-02-02T10:01:00-05:00'))
        p['inputs']['quotes']['A']['valid_until'] = '2026-02-02T10:00:20-05:00'
        p = preview(state, **p['inputs'])
        with self.assertRaisesRegex(ValueError, 'PAPER_QUOTE_EXPIRED'):
            transact(state, dict(kind='ACCEPT', operation_id='late', expected_revision=state['revision'],
                proposal=p, accepted_at='2026-02-02T10:00:30-05:00'))
        state = settle(accept(state, p))
        self.assertEqual(next(iter(state['orders'].values()))['closed'], 'FILLED')

    def test_touch_not_cross_and_missing_minute_unknown(self):
        state = accept(book(), proposal(book()))
        oid = next(iter(state['orders']))
        touched = settle(state, rows={oid:[bar(low='100')]})
        self.assertEqual(touched['cash'], '20000')
        self.assertIsNone(touched['orders'][oid]['closed'])
        missing = settle(state, rows={oid:[]})
        self.assertEqual(missing['operations'][-1]['outcome'][oid]['status'], 'UNKNOWN')
        self.assertEqual(missing['shares'], {})

    def test_idempotence_tamper_and_failed_transaction_unchanged(self):
        state = book(); p = proposal(state)
        request = dict(kind='ACCEPT', operation_id='same', expected_revision=state['revision'],
                       proposal=p, accepted_at=p['inputs']['now'])
        accepted = transact(state, request)
        self.assertEqual(transact(accepted, request), accepted)
        changed = deepcopy(request); changed['accepted_at']='2026-02-02T10:00:11-05:00'
        with self.assertRaisesRegex(ValueError, 'ID_CONFLICT'):
            transact(accepted, changed)
        corrupt = deepcopy(accepted); corrupt['cash']='999999'
        with self.assertRaisesRegex(ValueError, 'BOOK_REPLAY'):
            replay(corrupt)
        original = deepcopy(state); p['difference']['new_orders'][0]['quantity']=999
        with self.assertRaisesRegex(ValueError, 'PREVIEW_REPLAY'):
            accept(state, p)
        self.assertEqual(state, original)

    def test_no_unfilled_sales_finance_buys_and_simultaneous_batch(self):
        state = book()
        state = settle(accept(state, proposal(state, {'A': 190})))
        self.assertEqual(state['cash'], '1000')
        p = proposal(state, {'B': 20}, day='2026-02-03')
        buys = [o for o in p['difference']['new_orders'] if o['side']=='BUY']
        self.assertEqual(buys[0]['quantity'], 10)
        self.assertEqual(p['difference']['waiting_cash'][0]['quantity'], 10)
        state = settle(accept(state, p, 'rotate'), 'rotate-fill', '2026-02-03')
        self.assertEqual(state['shares'], {'A': 0, 'B': 10})
        self.assertEqual(Fraction(state['cash']), 19000)

    def test_scope_and_namespace_are_not_web_or_real(self):
        a = book()['application']
        for field, value in [('scope','WEB_MANUAL_ADVICE_RULE_ONLY'),('activation',True),
                             ('account_id','real-account'),('initial_cash','20001')]:
            changed=deepcopy(a); changed[field]=value
            with self.assertRaises(ValueError): create_book(changed)

    def test_late_source_cannot_rewrite_previous_observation(self):
        state = accept(book(), proposal(book()))
        oid = next(iter(state['orders']))
        state = settle(state, rows={oid:[]})
        request = dict(kind='SETTLE', operation_id='late', expected_revision=state['revision'],
            minutes={oid:[bar()]}, observed_through='2026-02-02T10:03:00-05:00',
            evaluated_at='2026-02-02T10:03:01-05:00')
        state = transact(state, request)
        self.assertEqual(state['cash'], '20000')
        self.assertEqual(state['operations'][-1]['outcome'][oid]['reason'], 'LATE_EVIDENCE_WOULD_REWRITE_HISTORY')

    def test_day_expiry_releases_reserve_and_partial_acceptance_minute_excluded(self):
        state = book(); p = proposal(state)
        p = preview(state, **dict(p['inputs'], session_close='2026-02-02T10:03:00-05:00'))
        state = accept(state, p)
        oid = next(iter(state['orders']))
        self.assertEqual(project(state)['available_cash'], '19000')
        rows = [bar(minute='10:00', low='90'), bar(minute='10:01', low='100'),
                bar(minute='10:02', low='100')]
        state = transact(state, dict(kind='SETTLE', operation_id='expire', expected_revision=state['revision'],
            minutes={oid:rows}, observed_through='2026-02-02T10:03:00-05:00',
            evaluated_at='2026-02-02T10:03:01-05:00'))
        self.assertEqual(state['orders'][oid]['closed'], 'EXPIRED')
        self.assertEqual(state['shares'], {})
        self.assertEqual(project(state)['available_cash'], '20000')

    def test_source_identity_error_is_atomic(self):
        state = accept(book(), proposal(book())); original = deepcopy(state)
        oid = next(iter(state['orders']))
        with self.assertRaisesRegex(ValueError, 'PAPER_MINUTE_IDENTITY'):
            settle(state, rows={oid:[bar(sid='WRONG')]})
        self.assertEqual(state, original)

    def test_late_evaluation_cannot_fund_earlier_preview_or_acceptance(self):
        state = accept(book(), proposal(book()))
        oid = next(iter(state['orders']))
        request = dict(kind='SETTLE', operation_id='late-evaluation', expected_revision=state['revision'],
            minutes={oid:[bar()]}, observed_through='2026-02-02T10:02:00-05:00',
            evaluated_at='2026-02-03T10:00:50-05:00')
        state = transact(state, request)
        self.assertEqual(state['last_observed_at'], '2026-02-02T10:02:00-05:00')
        self.assertEqual(state['last_available_at'], '2026-02-03T10:00:50-05:00')
        with self.assertRaisesRegex(ValueError, 'PREVIEW_BEFORE_STATE_AVAILABLE'):
            proposal(state, {'A': 20}, day='2026-02-03')
        # Construct a valid later preview, then backdate its acceptance. The
        # operation clock rejects before even considering proposal timestamps.
        original_inputs = proposal(book(), {'A': 20}, day='2026-02-03')['inputs']
        p = preview(state, **dict(original_inputs, now='2026-02-03T10:00:50-05:00'))
        with self.assertRaisesRegex(ValueError, 'OPERATION_AVAILABILITY_REVERSED'):
            transact(state, dict(kind='ACCEPT', operation_id='backdate', expected_revision=state['revision'],
                proposal=p, accepted_at='2026-02-03T10:00:10-05:00'))
        accepted = accept(state, p, 'proper-time')
        self.assertEqual(accepted['last_available_at'], '2026-02-03T10:00:50-05:00')

    def test_later_observation_cannot_hide_evaluation_clock_rollback(self):
        state = accept(book(), proposal(book()))
        oid = next(iter(state['orders']))
        state = transact(state, dict(kind='SETTLE', operation_id='first', expected_revision=state['revision'],
            minutes={oid:[]}, observed_through='2026-02-02T10:02:00-05:00',
            evaluated_at='2026-02-03T10:00:50-05:00'))
        original = deepcopy(state)
        with self.assertRaisesRegex(ValueError, 'OPERATION_AVAILABILITY_REVERSED'):
            transact(state, dict(kind='SETTLE', operation_id='rollback', expected_revision=state['revision'],
                minutes={oid:[]}, observed_through='2026-02-02T10:03:00-05:00',
                evaluated_at='2026-02-03T10:00:49-05:00'))
        self.assertEqual(state, original)
        self.assertEqual(replay(state), state)


if __name__ == '__main__':
    unittest.main()
