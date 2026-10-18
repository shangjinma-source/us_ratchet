import unittest
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
from unittest.mock import patch
from backtest.current_quantity_v2_risk_next_open import run_risk_next_open
from backtest.current_quantity_v2_risk_overlays import UNIT_SCHEMA
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from backtest.current_quantity_v2_signal_history import build_signal_history_resolver


def fixture():
    dates = []; day = date(2026, 1, 1)
    while len(dates) < 25:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += timedelta(days=1)
    prices = {day: str(10 if index % 2 else 11) for index, day in enumerate(dates)}
    prices.update({dates[20]:'11', dates[21]:'8', dates[22]:'12', dates[23]:'12', dates[24]:'12'})
    sessions = dates[20:]
    pins = {path:'a'*64 for path in REQUIRED_PINS}
    pins.update({'raw':'a'*64, 'backtest/return_priority_fresh_cash_quantity_search.py':'a'*64})
    args = dict(decision_date=sessions[0], quote_as_of=sessions[0], price_basis='TEST',
        prices={'A':prices[sessions[0]]}, metadata={'A':dict(ticker='A', issuer_id='A')},
        entered_cash='1000', fee_bps='0', minimum_cash_buffer='0',
        scenario_dates=dates[9:21], training_scenarios=[{'A':'11/10'} for _ in range(12)],
        max_objective_evaluations=128, fixed_seed='mechanism')
    assembled = dict(session_dates=sessions, monthly_inputs=[dict(decision_date=sessions[0],
        search_arguments=args, valuation_quotes=[dict(security_id='A', price=prices[sessions[0]],
        as_of=sessions[0], price_basis='TEST', source_references=['raw'])], source_hashes=pins)],
        close_prices={'A':prices}, provider_actions=[], actions=[], cash_stock_merger_events=[],
        fractional_settlements={}, price_source_references={'A':['raw']}, distribution_events=[],
        distribution_fractional_cash_values={})
    ohlc = {'A':{day:dict(open=prices[day], high=prices[day], low=prices[day], close=prices[day]) for day in sessions}}

    def resolver(*, decision_date, target_quantities, monthly_decision_date, count):
        index = dates.index(decision_date)
        window = dates[index-count+1:index+1]
        positive = {sid:q for sid,q in target_quantities.items() if q}
        units = dict(schema=UNIT_SCHEMA, unit_asof=decision_date, currency='USD',
                     basis_id='A:'+decision_date, review_reference='synthetic_review')
        return dict(observed_at=decision_date+'T16:01:00-05:00', session_dates=dates,
            session_close_times=dict(review_reference='synthetic_clock',
                closes={day:day+'T16:00:00-05:00' for day in dates}),
            base_target=dict(quantities=target_quantities, monthly_decision_date=monthly_decision_date,
                origin_reference='frozen', price_units={sid:units['basis_id'] for sid in positive}),
            histories={sid:dict(units=units, source_reference='raw', closes=[dict(date=day,
                close=prices[day], completed_at=day+'T16:00:00-05:00') for day in window]) for sid in positive})
    return assembled, ohlc, resolver


class RiskNextOpenTests(unittest.TestCase):
    def run_policy(self, policy, assembled, ohlc, resolver):
        return run_risk_next_open(policy=policy, assembled=assembled, ohlc=ohlc,
            initial_cash='1000', fee_bps='0', slippage_bps='0', history_resolver=resolver)

    def test_r1_monthly_scaled_target_does_not_rebound(self):
        a, bars, resolver = fixture(); result = self.run_policy('R1', a, bars, resolver)
        self.assertEqual(result['status'], 'COMPLETE')
        selections = [row['selection'] for row in result['provider_audit'] if row.get('selection')]
        self.assertEqual(len(selections), 1)
        selected = selections[0]
        scaled = selected['target_quantities']['A']
        self.assertLess(scaled, selected['raw_v2_selection']['target_quantities']['A'])
        self.assertTrue(all(row['target_shares']['A'] == scaled for row in result['provider_audit']))
        self.assertNotEqual(selected['overlay_decision_id'], selected['base_decision_id'])

    def test_r2_sells_then_reenters_only_monthly_ceiling(self):
        a, bars, resolver = fixture(); result = self.run_policy('R2', a, bars, resolver)
        self.assertEqual(result['status'], 'COMPLETE')
        audits = result['provider_audit']; ceiling = audits[0]['monthly_ceiling']['A']
        self.assertEqual(audits[1]['target_shares']['A'], 0)
        self.assertEqual(audits[2]['target_shares']['A'], ceiling)
        self.assertTrue(any(order['side']=='SELL' for order in audits[1]['orders']))
        self.assertTrue(any(order['side']=='BUY' for order in audits[2]['orders']))
        self.assertTrue(all(row['target_shares']['A'] <= ceiling for row in audits))

    def test_future_open_cannot_change_initial_signal(self):
        for policy in ('R1', 'R2'):
            a, bars, resolver = fixture(); first = self.run_policy(policy, a, bars, resolver)
            changed = deepcopy(bars); day = a['session_dates'][1]
            changed['A'][day] = dict(open='999', high='999', low='8', close='8')
            second = self.run_policy(policy, a, changed, resolver)
            self.assertEqual(first['provider_audit'][0], second['provider_audit'][0])

    def test_missing_or_wrong_unit_history_blocks_not_empty_success(self):
        for policy in ('R1', 'R2'):
            for failure in ('missing', 'unit'):
                a, bars, resolver = fixture()
                def invalid(**kwargs):
                    data = resolver(**kwargs)
                    if failure == 'missing':
                        data['histories'] = {}
                    else:
                        data['histories']['A']['closes'][-1]['close'] = '999'
                    return data
                result = self.run_policy(policy, a, bars, invalid)
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertEqual(result['provider_audit'][0]['status'], 'BLOCKED')
                self.assertTrue(result['raw_selection_attempts'])

    def test_incomplete_v2_selection_never_calls_resolver(self):
        a, bars, _ = fixture()
        def never(**kwargs):
            self.fail('Incomplete V2 must not reach history resolver')
        with patch('backtest.current_quantity_v2_risk_next_open.decide_quantity_v2_for_account',
                   return_value=dict(target_quantities=None)):
            result = self.run_policy('R1', a, bars, never)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['provider_audit'][0]['reason'], 'MONTHLY_SELECTION_INCOMPLETE')

    def test_future_observation_cannot_be_backdated_to_signal(self):
        a, bars, resolver = fixture()
        def future(**kwargs):
            data = resolver(**kwargs); data['observed_at'] = '2099-01-01T16:01:00-05:00'
            return data
        for policy in ('R1', 'R2'):
            result = self.run_policy(policy, a, bars, future)
            self.assertEqual(result['status'], 'BLOCKED')

    def test_reviewed_snapshot_resolver_integration(self):
        a, bars, source = fixture(); snapshots = {}; sample = None
        for day in a['session_dates'][:-1]:
            sample = source(decision_date=day, target_quantities={'A':1},
                            monthly_decision_date=a['session_dates'][0], count=21)
            snapshots[day] = dict(observed_at=sample['observed_at'],
                review_reference='snapshot:'+day, histories=sample['histories'])
        resolver = build_signal_history_resolver(session_dates=sample['session_dates'],
            session_close_times=sample['session_close_times'], snapshots=snapshots)
        for policy in ('R1', 'R2'):
            result = self.run_policy(policy, a, bars, resolver)
            self.assertEqual(result['status'], 'COMPLETE')

    def test_active_day_split_migrates_scaled_target_and_ceiling_once(self):
        a, bars, source = fixture()
        split_day = a['session_dates'][1]
        event = dict(type='split', date=split_day, security_id='A', new_shares=2,
                     old_shares=1, source_references=['raw'])
        a['actions'] = [event]; a['provider_actions'] = [event]
        for day in a['session_dates'][1:]:
            a['close_prices']['A'][day] = str(Fraction(a['close_prices']['A'][day]) / 2)
            bars['A'][day] = {key:str(Fraction(value)/2) for key,value in bars['A'][day].items()}
        def normalized(**kwargs):
            data = source(**kwargs)
            if kwargs['decision_date'] >= split_day:
                for history in data['histories'].values():
                    for row in history['closes']:
                        if row['date'] < split_day:
                            row['close'] = str(Fraction(row['close']) / 2)
            return data
        for policy in ('R1', 'R2'):
            result = self.run_policy(policy, a, bars, normalized)
            self.assertEqual(result['status'], 'COMPLETE')
            audits = result['provider_audit']
            initial = audits[0]['monthly_ceiling']['A']
            self.assertTrue(all(row['monthly_ceiling']['A'] == 2*initial for row in audits[1:]))
            self.assertEqual(len(result['raw_selection_attempts']), 1)
            if policy == 'R1':
                self.assertTrue(all(row['target_shares']['A'] == 2*initial for row in audits[1:]))
                self.assertLess(initial, audits[0]['selection']['raw_v2_selection']['target_quantities']['A'])
            else:
                self.assertEqual(audits[1]['target_shares']['A'], 0)
                self.assertEqual(audits[2]['target_shares']['A'], 2*initial)


if __name__ == '__main__':
    unittest.main()
