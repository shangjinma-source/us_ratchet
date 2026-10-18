import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from test_current_quantity_v2_paper_ledger import initial
from test_current_quantity_v2_paper_chain import inputs
import test_current_quantity_v2_difference_plan as difference_fixtures
from data.current_quantity_v2_difference_plan import build_account_difference_plan
from data.current_quantity_v2_paper_ledger import accept_proposal
from data.current_quantity_v2_paper_chain import create_chain, review_chain, build_continuation
from backtest.current_quantity_v2_simulated_settlement import (
    create_simulation, settle, accept_orders, register_valuation, record_close, MODEL)


def fixture(two_buys=False):
    ledger, _, args = initial()
    if two_buys:
        d = args['capital_decision']; b = d['binding']
        args['account_state']['cash'] = b['available_cash'] = d['available_cash'] = '20.01'
        b['valuation_quotes']['X']['price'] = '39.995'; d['holding_market_values']['X'] = '79.99'
        b['search_arguments']['prices']['B'] = '1'
        b['search_arguments']['metadata']['B'] = dict(ticker='BBB', issuer_id='ib')
        d['target_quantities'] = {'A': 25, 'B': 25}
        d['search_result']['selected'].update(quantities={'A': 25, 'B': 25}, actual_weights={'A': '1/4', 'B': '1/4'}, actual_k=2)
        args['securities']['B'] = dict(ticker='BBB', issuer_id='ib')
        for key in ('execution_references', 'unit_continuity'):
            args[key]['B'] = dict(args[key]['A'], security_id='B', ticker='BBB')
        difference_fixtures.DifferenceTests.rebind(None, args)
        p = build_account_difference_plan(**args)
        ledger = accept_proposal(p, account_state=args['account_state'], now=args['now'])
    state = create_simulation(chain=create_chain(ledger), simulation_id='isolated-test', model=MODEL)
    evidence = {}
    for oid, order in ledger['orders'].items():
        sid = order['security_id']
        identity = dict(security_id=sid, ticker=args['securities'][sid]['ticker'], session='2026-10-15')
        price = '51' if order['side'] == 'SELL' else '.9'
        evidence[oid] = dict(identity, fees='0', source_reference='synthetic-test', minutes=[dict(identity,
            start='2026-10-15T12:01:00-04:00', end='2026-10-15T12:02:00-04:00',
            open=price, high=price, low=price, close=price)])
    return state, evidence, args


def run(state, evidence, at='2026-10-15T12:02:00-04:00'):
    return settle(simulation=state, evidence=evidence, observed_through=at, evaluated_at=at)


def later_inputs(args, at, chain=None):
    result = {k: deepcopy(args[k]) for k in ('securities', 'execution_references', 'unit_continuity', 'source_hashes')}
    moment = datetime.fromisoformat(at)
    for ref in result['execution_references'].values():
        ref.update(session=at[:10], captured_at=at, checked_at=at,
            last_at=(moment-timedelta(seconds=5)).isoformat(),
            minute_start=(moment.replace(second=0)-timedelta(minutes=1)).isoformat(),
            minute_end=moment.replace(second=0).isoformat(),
            valid_until=(moment.replace(second=0)+timedelta(minutes=2)).isoformat(),
            session_open=moment.replace(hour=9, minute=30, second=0).isoformat(),
            session_close=moment.replace(hour=16, minute=0, second=0).isoformat())
    for unit in result['unit_continuity'].values(): unit.update(covered_through=at, reviewed_at=at)
    if chain is not None:
        ledger = chain['ledger']
        needed = {sid for sid, q in ledger['shares'].items() if q} | {sid for sid, q in ledger['target_quantities'].items() if q}
        for key in ('securities', 'execution_references', 'unit_continuity'):
            result[key] = {sid: row for sid, row in result[key].items() if sid in needed}
    return result


def evidence_for(chain, references, *, fill=True, full_day=False):
    evidence = {}; through = None
    for oid, order in chain['ledger']['orders'].items():
        sid = order['security_id']; ref = references[sid]
        accepted = datetime.fromisoformat(order['accepted_at'])
        first = accepted.replace(second=0, microsecond=0)
        if first < accepted: first += timedelta(minutes=1)
        end = datetime.fromisoformat(order['session_close']) if full_day else first+timedelta(minutes=1)
        identity = dict(security_id=sid, ticker=ref['ticker'], session=ref['session'])
        low_price = (order['side'] == 'BUY') == fill
        price = str(Fraction(order['limit_price']) * (Fraction(1, 2) if low_price else 2))
        evidence[oid] = dict(identity, source_reference='synthetic-followup', fees='0', minutes=[dict(identity,
            start=(first+timedelta(minutes=i)).isoformat(), end=(first+timedelta(minutes=i+1)).isoformat(),
            open=price, high=price, low=price, close=price) for i in range(int((end-first).total_seconds()/60))])
        through = end.isoformat()
    return evidence, through


def mark(sid, ticker, price, at, observed=None):
    return dict(security_id=sid, ticker=ticker, price=price, session=at[:10], currency='USD',
        price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS', as_of=at,
        observed_at=observed or at, source_references=['synthetic-mark'])


def valuation_fixture():
    state, evidence, args = fixture()
    calendar = dict(session_dates=['2026-10-15', '2026-10-16'], source_references=['synthetic-calendar'],
        closes={d:d+'T16:00:00-04:00' for d in ['2026-10-15','2026-10-16']})
    accepted = args['now']
    registered = register_valuation(simulation=state, calendar=calendar,
        initial_marks={'X':mark('X','XXX','50',accepted)}, registered_at=accepted)
    return registered, evidence, args, calendar


class SimulatedSettlementTests(unittest.TestCase):
    def test_cash_only_close_after_sale_and_expiry_needs_no_stock_marks(self):
        state,_,args,_=valuation_fixture()
        evidence,through=evidence_for(state['chain'],args['execution_references'],fill=False,full_day=True)
        for oid,item in evidence.items():
            if state['chain']['ledger']['orders'][oid]['side']=='SELL':
                for bar in item['minutes']:bar.update(open='51',high='51',low='51',close='51')
        flat=run(state,evidence,through)
        self.assertFalse(any(flat['chain']['ledger']['shares'].values()))
        first=record_close(simulation=flat,session='2026-10-15',marks={},observed_at='2026-10-15T16:01:00-04:00')
        second=record_close(simulation=first,session='2026-10-16',marks={},observed_at='2026-10-16T16:01:00-04:00')
        self.assertEqual(second['valuation']['records'][-1]['equity'],'6001/50')
        self.assertEqual(second['valuation']['performance']['drawdown']['maximum_close_drawdown'],'0')
        self.assertEqual(second['valuation']['performance']['cumulative_return'],'1/6000')

    def test_close_nav_non_cash_initial_and_cross_day_trade_loss(self):
        state, evidence, args, _ = valuation_fixture()
        self.assertEqual(state['valuation']['initial_equity'], '120')
        first = run(state, evidence)
        first = record_close(simulation=first, session='2026-10-15',
            marks={'A':mark('A','AAA','1','2026-10-15T16:00:00-04:00')}, observed_at='2026-10-15T16:01:00-04:00')
        self.assertEqual(first['valuation']['records'][0]['equity'], '6001/50')
        at = '2026-10-16T12:00:30-04:00'
        refs = later_inputs(args,at,first['chain'])
        p = build_continuation(first['chain'],execution_inputs=refs,now=at)
        continued = accept_orders(simulation=first,proposal=p,acceptance_id='after-close',accepted_at=at)
        evidence2, through = evidence_for(continued['chain'],refs['execution_references'])
        second = run(continued,evidence2,through)
        marks = {'A':mark('A','AAA','1/2','2026-10-16T16:00:00-04:00')}
        second = record_close(simulation=second,session='2026-10-16',marks=marks,observed_at='2026-10-16T16:01:00-04:00')
        performance = second['valuation']['performance']
        self.assertEqual(performance['current_equity'],'4751/50')
        self.assertEqual(performance['cumulative_return'],'-1249/6000')
        self.assertEqual(performance['drawdown']['maximum_close_drawdown'],'1250/6001')
        self.assertFalse(performance['calendar_authenticated'])
        self.assertEqual(record_close(simulation=second,session='2026-10-16',marks=marks,
            observed_at='2026-10-16T16:01:00-04:00'),second)
        self.assertEqual(review_chain(second['chain']),second['chain'])

    def test_missing_losing_mark_retained_and_cannot_skip_or_replace(self):
        state,evidence,_,_=valuation_fixture(); state=run(state,evidence)
        with self.assertRaisesRegex(ValueError,'NEXT_DECLARED_SESSION'):
            record_close(simulation=state,session='2026-10-16',marks={},observed_at='2026-10-16T16:01:00-04:00')
        missing=record_close(simulation=state,session='2026-10-15',marks={},observed_at='2026-10-15T16:01:00-04:00')
        self.assertIsNone(missing['valuation']['records'][0]['equity'])
        self.assertEqual(missing['valuation']['records'][0]['missing_marks'],['A'])
        with self.assertRaisesRegex(ValueError,'NEXT_DECLARED_SESSION'):
            record_close(simulation=missing,session='2026-10-15',marks={'A':mark('A','AAA','1/2','2026-10-15T16:00:00-04:00')},
                observed_at='2026-10-15T16:02:00-04:00')
        later=record_close(simulation=missing,session='2026-10-16',marks={'A':mark('A','AAA','1/2','2026-10-16T16:00:00-04:00')},
            observed_at='2026-10-16T16:01:00-04:00')
        self.assertEqual(later['valuation']['performance']['status'],'INCOMPLETE')
        self.assertIsNone(later['valuation']['performance']['cumulative_return'])
        self.assertIsNone(later['valuation']['performance']['drawdown'])

    def test_initial_marks_timing_identity_and_unresolved_orders(self):
        state,evidence,args,calendar=valuation_fixture()
        plain,_,_=fixture()
        with self.assertRaisesRegex(ValueError,'INITIAL_EQUITY'):
            register_valuation(simulation=plain,calendar=calendar,initial_marks={},registered_at=args['now'])
        filled=run(plain,evidence)
        with self.assertRaisesRegex(ValueError,'REGISTER_BEFORE'):
            register_valuation(simulation=filled,calendar=calendar,initial_marks={'X':mark('X','XXX','50',args['now'])},registered_at=args['now'])
        unresolved=record_close(simulation=state,session='2026-10-15',marks={'X':mark('X','XXX','1','2026-10-15T16:00:00-04:00')},
            observed_at='2026-10-15T16:01:00-04:00')
        self.assertIsNone(unresolved['valuation']['records'][0]['equity'])
        self.assertTrue(unresolved['valuation']['records'][0]['unresolved_orders'])
        filled=run(state,evidence)
        for change in ({'ticker':'BAD'},{'currency':'CAD'},{'price_basis':'ADJUSTED'}, {'session':'2026-10-14'}):
            bad=mark('A','AAA','1','2026-10-15T16:00:00-04:00');bad.update(change)
            with self.assertRaisesRegex(ValueError,'IDENTITY_OR_UNIT'):
                record_close(simulation=filled,session='2026-10-15',marks={'A':bad},observed_at='2026-10-15T16:01:00-04:00')
        with self.assertRaisesRegex(ValueError,'CLOSE_NOT_OBSERVED'):
            record_close(simulation=filled,session='2026-10-15',marks={},observed_at='2026-10-15T15:59:00-04:00')
        marked=record_close(simulation=filled,session='2026-10-15',marks={'A':mark('A','AAA','1','2026-10-15T16:00:00-04:00')},
            observed_at='2026-10-15T16:01:00-04:00')
        with self.assertRaisesRegex(ValueError,'SIMULATION_TIME_REVERSED'):
            accept_orders(simulation=marked,proposal={},acceptance_id='backdated',accepted_at='2026-10-15T15:59:00-04:00')

    def test_next_day_expiry_continuation_carries_cash_and_no_unfilled_sale_funding(self):
        state, _, args = fixture()
        evidence, through = evidence_for(state['chain'], args['execution_references'], fill=False, full_day=True)
        expired = run(state, evidence, through)
        at = '2026-10-16T12:00:30-04:00'
        next_inputs = later_inputs(args, at)
        proposal = build_continuation(expired['chain'], execution_inputs=next_inputs, now=at)
        self.assertEqual(next(o['quantity'] for o in proposal['orders'] if o['side']=='BUY'), 20)
        accepted = accept_orders(simulation=expired, proposal=proposal, acceptance_id='next-day', accepted_at=at)
        self.assertEqual(accepted['chain']['ledger']['cash'], '20')
        self.assertEqual(accepted['chain']['ledger']['shares'], {'X': 2})
        self.assertEqual(accept_orders(simulation=accepted, proposal=proposal, acceptance_id='next-day',
            accepted_at='2027-01-01T00:00:00+00:00'), accepted)
        self.assertEqual(run(accepted, evidence, through), accepted)  # old exact settlement retry
        new_evidence, new_through = evidence_for(accepted['chain'], next_inputs['execution_references'])
        settled = run(accepted, new_evidence, new_through)
        self.assertEqual(settled['chain']['ledger']['cash'], '5001/50')
        self.assertEqual(settled['chain']['ledger']['shares'], {'X': 0, 'A': 20})
        self.assertEqual(review_chain(settled['chain']), settled['chain'])
        # Only after actual modeled sale and prior orders closing can cash fund the deficit.
        later_at = '2026-10-16T12:03:30-04:00'
        follow_inputs = later_inputs(args, later_at, settled['chain'])
        follow = build_continuation(settled['chain'], execution_inputs=follow_inputs, now=later_at)
        self.assertEqual(follow['orders'][0]['quantity'], 30)
        continued = accept_orders(simulation=settled, proposal=follow, acceptance_id='funded-after-sale', accepted_at=later_at)
        self.assertEqual(continued['chain']['ledger']['cash'], '5001/50')
        evidence2, through2 = evidence_for(continued['chain'], follow_inputs['execution_references'])
        complete = run(continued, evidence2, through2)
        self.assertEqual(complete['chain']['ledger']['shares']['A'], 50)
        self.assertEqual(complete['chain']['ledger']['cash'], '3501/50')
        self.assertEqual(run(complete, evidence2, through2), complete)

    def test_monthly_new_stock_identity_settlement_and_continuation(self):
        import test_current_quantity_v2_monthly_retarget as monthly_fixtures
        from data.current_quantity_v2_monthly_retarget import build_monthly_retarget
        state, evidence, args = fixture()
        settled = run(state, evidence)
        chain, monthly_args, at = monthly_fixtures.fixture((settled['chain'], args))
        proposal = build_monthly_retarget(chain, proposal_inputs=monthly_args, now=at)
        accepted = accept_orders(simulation=settled, proposal=proposal, acceptance_id='new-month',
            accepted_at=at, kind='MONTHLY_RETARGET')
        self.assertEqual(accepted['chain']['ledger']['cash'], settled['chain']['ledger']['cash'])
        self.assertEqual(accepted['chain']['ledger']['target_quantities'], proposal['target_quantities'])
        self.assertIn('B', proposal['target_quantities'])
        evidence, through = evidence_for(accepted['chain'], monthly_args['execution_references'], fill=False, full_day=True)
        for oid, item in evidence.items():
            if accepted['chain']['ledger']['orders'][oid]['side'] == 'SELL':
                price = str(Fraction(accepted['chain']['ledger']['orders'][oid]['limit_price']) * 2)
                for bar in item['minutes']: bar.update(open=price, high=price, low=price, close=price)
        wrong = deepcopy(evidence)
        for item in wrong.values():
            if item['security_id'] == 'B': item['ticker'] = 'AAA'
        with self.assertRaisesRegex(ValueError, 'IDENTITY'): run(accepted, wrong, through)
        filled = run(accepted, evidence, through)
        self.assertEqual(filled['chain']['ledger']['shares'].get('B', 0), 0)
        self.assertEqual(filled['chain']['ledger']['shares']['A'], 0)
        self.assertEqual(review_chain(filled['chain']), filled['chain'])
        follow_at = '2026-11-03T12:00:30-05:00'
        refs = later_inputs(monthly_args, follow_at, filled['chain'])
        follow = build_continuation(filled['chain'], execution_inputs=refs, now=follow_at)
        self.assertTrue(follow['orders'])
        accepted2 = accept_orders(simulation=filled, proposal=follow, acceptance_id='new-month-follow', accepted_at=follow_at)
        evidence2, through2 = evidence_for(accepted2['chain'], refs['execution_references'])
        final = run(accepted2, evidence2, through2)
        self.assertEqual(review_chain(final['chain']), final['chain'])
        self.assertEqual(final['chain']['ledger']['shares']['B'], proposal['target_quantities']['B'])
        self.assertEqual(final['chain']['ledger']['shares']['A'], 0)
        self.assertEqual(final['chain']['ledger']['cash'], '2501/50')
        changed = deepcopy(proposal); changed['target_quantities']['B'] += 1
        with self.assertRaisesRegex(ValueError, 'ACCEPTANCE_ID_CONFLICT'):
            accept_orders(simulation=filled, proposal=changed, acceptance_id='new-month', accepted_at=at, kind='MONTHLY_RETARGET')

    def test_unknown_observation_blocks_backdated_accept_and_manual_state(self):
        state, evidence, args = fixture()
        for item in evidence.values(): item['minutes'] = []
        unknown = run(state, evidence, '2026-10-16T12:00:00-04:00')
        with self.assertRaisesRegex(ValueError, 'SIMULATION_TIME_REVERSED'):
            accept_orders(simulation=unknown, proposal={}, acceptance_id='retro', accepted_at='2026-10-15T13:00:00-04:00')
        tampered = deepcopy(unknown); tampered['chain']['ledger']['cash'] = '500'
        with self.assertRaisesRegex(ValueError, 'MIXED'):
            accept_orders(simulation=tampered, proposal={}, acceptance_id='bad', accepted_at='2026-10-16T12:00:00-04:00')

    def test_two_sides_replay_idempotence_and_continuation(self):
        state, evidence, args = fixture()
        result = run(state, evidence)
        ledger = result['chain']['ledger']
        self.assertEqual(ledger['cash'], '5001/50')
        self.assertEqual(ledger['shares'], {'A': 20, 'X': 0})
        self.assertEqual(ledger['reserved_cash'], '0')
        self.assertEqual(review_chain(result['chain']), result['chain'])
        self.assertEqual(run(result, evidence), result)
        self.assertEqual(state['chain']['ledger']['events'], [])
        proposal = build_continuation(result['chain'], execution_inputs=inputs(args), now='2026-10-15T13:03:30-04:00')
        self.assertEqual(proposal['orders'][0]['quantity'], 30)

    def test_same_time_sales_cannot_fund_fees(self):
        state, evidence, _ = fixture()
        for item in evidence.values():
            item['fees'] = '.01'
        result = run(state, evidence)
        self.assertEqual(result['chain'], state['chain'])
        self.assertTrue(all(item['status'] == 'UNKNOWN' for item in result['batches'][-1]['results'].values()))

    def test_sell_fee_uses_own_proceeds_and_earlier_sale_can_fund_later_buy_fee(self):
        state, evidence, _ = fixture()
        sell = next(k for k, v in state['chain']['ledger']['orders'].items() if v['side'] == 'SELL')
        buy = next(k for k in evidence if k != sell)
        evidence[sell]['fees'] = '.01'
        evidence[buy]['fees'] = '.02'
        evidence[buy]['minutes'][0].update(open='2', high='2', low='2', close='2')
        bar = deepcopy(evidence[buy]['minutes'][0])
        bar.update(start='2026-10-15T12:02:00-04:00', end='2026-10-15T12:03:00-04:00',
                   open='.9', high='.9', low='.9', close='.9')
        evidence[buy]['minutes'].append(bar)
        result = run(state, evidence, '2026-10-15T12:03:00-04:00')
        self.assertEqual(result['chain']['ledger']['recorded_fees'], '3/100')
        self.assertEqual(result['chain']['ledger']['cash'], '9999/100')
        self.assertEqual(len(result['chain']['ledger']['events']), 2)

    def test_missing_minutes_unknown_and_late_evidence_not_rewritten(self):
        state, evidence, _ = fixture()
        buy = next(k for k, v in state['chain']['ledger']['orders'].items() if v['side'] == 'BUY')
        missing = deepcopy(evidence)
        missing[buy]['minutes'] = []
        result = run(state, missing)
        self.assertEqual(result['batches'][-1]['results'][buy]['status'], 'UNKNOWN')
        # A later batch cannot insert an earlier fill behind an already recorded event.
        sell = next(k for k in evidence if k != buy)
        delayed = deepcopy(evidence)
        for bar in delayed[sell]['minutes']:
            bar.update(high='49', low='49', open='49', close='49')
        extra = deepcopy(delayed[sell]['minutes'][0])
        extra.update(start='2026-10-15T12:02:00-04:00', end='2026-10-15T12:03:00-04:00',
                     open='51', high='51', low='51', close='51')
        delayed[sell]['minutes'].append(extra)
        delayed[buy]['minutes'] = []
        later = run(state, delayed, '2026-10-15T12:03:00-04:00')
        delayed[buy] = evidence[buy]
        final = run(later, delayed, '2026-10-15T12:03:00-04:00')
        self.assertEqual(final['batches'][-1]['results'][buy]['reason'], 'LATE_EVIDENCE_WOULD_REWRITE_HISTORY')

    def test_late_same_time_buy_cannot_reuse_already_recorded_sale_cash(self):
        state, evidence, _ = fixture()
        buy = next(k for k, v in state['chain']['ledger']['orders'].items() if v['side'] == 'BUY')
        evidence[buy]['fees'] = '1'
        missing = deepcopy(evidence); missing[buy]['minutes'] = []
        sold = run(state, missing)
        final = run(sold, evidence)
        self.assertEqual(final['batches'][-1]['results'][buy]['reason'], 'LATE_EVIDENCE_WOULD_REWRITE_HISTORY')
        self.assertEqual(final['chain'], sold['chain'])

    def test_identity_future_and_mixed_state_rejected(self):
        state, evidence, _ = fixture()
        oid = next(iter(evidence))
        bad = deepcopy(evidence); bad[oid]['minutes'][0]['ticker'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'IDENTITY'): run(state, bad)
        bad = deepcopy(evidence); bad[oid]['session'] = '2026-10-14'
        with self.assertRaisesRegex(ValueError, 'IDENTITY'): run(state, bad)
        with self.assertRaisesRegex(ValueError, 'FUTURE'):
            settle(simulation=state, evidence=evidence, observed_through='2026-10-15T12:03:00-04:00', evaluated_at='2026-10-15T12:02:00-04:00')
        mixed = deepcopy(state); mixed['chain']['ledger']['cash'] = '100000'
        with self.assertRaisesRegex(ValueError, 'MIXED'): run(mixed, evidence)

    def test_two_buys_cannot_reuse_same_fee_budget_and_fee_convention_freezes(self):
        state, evidence, _ = fixture(two_buys=True)
        buy_ids = [oid for oid, order in state['chain']['ledger']['orders'].items() if order['side'] == 'BUY']
        self.assertEqual(len(buy_ids), 2)
        for oid in buy_ids: evidence[oid]['fees'] = '.01'
        result = run(state, evidence)
        self.assertEqual(result['chain'], state['chain'])
        self.assertTrue(all(result['batches'][-1]['results'][oid]['status'] == 'UNKNOWN' for oid in buy_ids))
        changed = deepcopy(evidence); changed[buy_ids[0]]['fees'] = '0'
        with self.assertRaisesRegex(ValueError, 'REGISTERED_ORDER_FEES_CHANGED'): run(result, changed)
        # No fees: both reserved buys settle, without either consuming the other's reservation.
        for oid in buy_ids: evidence[oid]['fees'] = '0'
        filled = run(state, evidence)
        self.assertEqual(filled['chain']['ledger']['shares']['A'], 10)
        self.assertEqual(filled['chain']['ledger']['shares']['B'], 10)
        self.assertEqual(review_chain(filled['chain']), filled['chain'])

    def test_full_day_no_cross_expires_without_cash_change(self):
        state, evidence, _ = fixture()
        for oid, item in evidence.items():
            price = '49' if state['chain']['ledger']['orders'][oid]['side'] == 'SELL' else '2'
            start = datetime.fromisoformat('2026-10-15T12:01:00-04:00')
            item['minutes'] = [dict(security_id=item['security_id'], ticker=item['ticker'], session=item['session'],
                start=(start+timedelta(minutes=i)).isoformat(), end=(start+timedelta(minutes=i+1)).isoformat(),
                open=price, high=price, low=price, close=price) for i in range(239)]
        result = run(state, evidence, '2026-10-15T16:00:00-04:00')
        self.assertEqual(result['chain']['ledger']['cash'], '20')
        self.assertEqual(result['chain']['ledger']['reserved_cash'], '0')
        self.assertTrue(all(v['closed'] == 'EXPIRED' for v in result['chain']['ledger']['orders'].values()))
        # A sell crossing at the final minute has an unaffordable own fee;
        # the simultaneous BUY expiry must still release its reservation.
        sell = next(k for k, v in state['chain']['ledger']['orders'].items() if v['side'] == 'SELL')
        evidence[sell]['fees'] = '101'
        evidence[sell]['minutes'][-1].update(open='51', high='51', low='51', close='51')
        result = run(state, evidence, '2026-10-15T16:00:00-04:00')
        self.assertEqual(result['batches'][-1]['results'][sell]['status'], 'UNKNOWN')
        self.assertEqual(result['chain']['ledger']['reserved_cash'], '0')
        self.assertEqual(result['chain']['ledger']['cash'], '20')
        self.assertEqual(len(result['chain']['ledger']['events']), 1)
        # Expiry's identifier sorts first, but effective time must put the
        # final-minute fill before the close-time expiry in the same batch.
        evidence[sell]['fees'] = '0'
        evidence[sell]['minutes'][-1].update(open='49', high='49', low='49', close='49')
        buy = next(k for k in evidence if k != sell)
        self.assertLess(sell, buy)
        evidence[buy]['minutes'][-1].update(open='.9', high='.9', low='.9', close='.9')
        result = run(state, evidence, '2026-10-15T16:00:00-04:00')
        self.assertEqual([e['type'] for e in result['chain']['ledger']['events']], ['FILL', 'EXPIRE'])
        self.assertEqual(result['chain']['ledger']['orders'][buy]['closed'], 'FILLED')


if __name__ == '__main__': unittest.main()
