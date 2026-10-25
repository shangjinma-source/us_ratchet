from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch
import test_continuous_guided_cost_stress as fixtures
from backtest.continuous_guided_cost_stress import prepare_arm, SCENARIOS
from backtest.continuous_guided_monthly_latched_half_next_open import run_cost_monthly_latched_half_next_open
from backtest.monthly_latched_half_state import MonthlyHalfLatch
from backtest import continuous_guided_account_decision as selector
from backtest import continuous_guided_monthly_latched_half_next_open as candidate


def risk(month, ceilings, signals):
    return dict(base_target=dict(monthly_decision_date=month, quantities=deepcopy(ceilings)),
        diagnostics={sid:dict(on=value) for sid,value in signals.items()}, target_quantities={})


class LatchStateTests(unittest.TestCase):
    def test_first_weak_latches_each_security_without_compounding(self):
        latch=MonthlyHalfLatch();latch.advance('2026-01-29')
        ceiling={'A':7,'B':8}
        out=latch.apply(risk('2026-01-29',ceiling,{'A':False,'B':True}),ceiling)
        self.assertEqual(out['target_quantities'],{'A':3,'B':8})
        for _ in range(3):
            out=latch.apply(risk('2026-01-29',ceiling,{'A':True,'B':True}),ceiling)
            self.assertEqual(out['target_quantities'],{'A':3,'B':8})

    def test_reset_only_on_new_target_and_immediate_relatch(self):
        latch=MonthlyHalfLatch();latch.advance('2026-01-29')
        ceiling={'A':1}
        latch.apply(risk('2026-01-29',ceiling,{'A':False}),ceiling)
        latch.advance('2026-01-29')
        self.assertEqual(latch.apply(risk('2026-01-29',ceiling,{'A':True}),ceiling)['target_quantities'],{'A':0})
        latch.advance('2026-02-02')
        self.assertEqual(latch.apply(risk('2026-02-02',ceiling,{'A':True}),ceiling)['target_quantities'],{'A':1})
        latch.advance('2026-03-02')
        self.assertEqual(latch.apply(risk('2026-03-02',ceiling,{'A':False}),ceiling)['target_quantities'],{'A':0})

    def test_supported_identity_migration_during_wait_preserves_latch(self):
        latch=MonthlyHalfLatch();latch.advance('2026-01-29')
        latch.apply(risk('2026-01-29',{'A':7},{'A':False}),{'A':7})
        latch.advance(None,[dict(security_id='A',new_security_id='B',target_after=14)])
        self.assertEqual(latch.apply(risk('2026-01-29',{'B':14},{'B':True}),{'B':14})['target_quantities'],{'B':7})
        latch.advance(None,[dict(security_id='B',new_security_id='B',target_after=28)])
        self.assertEqual(latch.apply(risk('2026-01-29',{'B':28},{'B':True}),{'B':28})['target_quantities'],{'B':14})

    def test_invalid_month_and_nonboolean_signal_rejected(self):
        latch=MonthlyHalfLatch();latch.advance('2026-01-29')
        with self.assertRaises(ValueError):latch.advance('2025-12-01')
        with self.assertRaises(ValueError):latch.apply(risk('2026-01-29',{'A':7},{'A':1}),{'A':7})
        self.assertEqual(latch.latched,set())

    def test_successful_new_month_ignores_old_identity_latch(self):
        latch=MonthlyHalfLatch();latch.advance('2026-01-29')
        latch.apply(risk('2026-01-29',{'A':7},{'A':False}),{'A':7})
        latch.advance('2026-02-02',[dict(security_id='A',new_security_id='B',target_after=14)])
        self.assertEqual(latch.apply(risk('2026-02-02',{'B':15},{'B':True}),{'B':15})['target_quantities'],{'B':15})
        self.assertEqual(latch.apply(risk('2026-02-02',{'B':15},{'B':False}),{'B':15})['target_quantities'],{'B':7})


class LatchBookTests(unittest.TestCase):
    def data(self,scenario):
        a,b,r=fixtures.CostStressTests().data()
        return prepare_arm(a,scenario),b,r

    def run_book(self,a,b,r,scenario):
        return run_cost_monthly_latched_half_next_open(assembled=a,ohlc=b,initial_cash='1000',
            history_resolver=r,**SCENARIOS[scenario])

    def test_no_monthly_recovery_even_across_calendar_month(self):
        for scenario in SCENARIOS:
            a,b,r=self.data(scenario);out=self.run_book(a,b,r,scenario)
            self.assertEqual(out['status'],'COMPLETE')
            rows=out['provider_audit'];ceiling=rows[0]['monthly_ceiling']['A']
            self.assertEqual(rows[1]['target_shares']['A'],ceiling//2)
            self.assertTrue(rows[2]['risk_overlay']['diagnostics']['A']['on'])
            self.assertEqual(rows[2]['target_shares']['A'],ceiling//2)
            self.assertNotEqual(a['session_dates'][1][:7],a['session_dates'][2][:7])

    def test_successful_monthly_reselection_resets_from_own_account(self):
        a,b,r=self.data('fee1_slippage10');day=a['session_dates'][2]
        second=deepcopy(a['monthly_inputs'][0]);second['decision_date']=day
        second['search_arguments'].update(decision_date=day,quote_as_of=day,prices={'A':a['close_prices']['A'][day]})
        second['valuation_quotes'][0].update(as_of=day,price=a['close_prices']['A'][day]);a['monthly_inputs'].append(second)
        with patch.object(selector,'original_search',wraps=selector.original_search) as calls:
            out=self.run_book(a,b,r,'fee1_slippage10')
        self.assertEqual(out['status'],'COMPLETE');self.assertEqual(calls.call_count,2)
        row=out['provider_audit'][2]
        self.assertEqual(row['target_shares'],row['monthly_ceiling'])
        self.assertEqual(row['risk_overlay']['monthly_latch']['latched_security_ids'],[])
        state=out['selection_account_states'][1]['account_state']
        ledger=next(row for row in out['daily_ledger'] if row['date']==day)
        self.assertEqual((state['cash'],state['shares']),(ledger['cash'],ledger['shares']))
        wealth=Fraction(state['cash'])+sum(q*Fraction(a['close_prices'][sid][day]) for sid,q in state['shares'].items())
        self.assertEqual(Fraction(calls.call_args_list[1].kwargs['entered_cash']),wealth)

    def test_future_open_does_not_change_prior_selection_and_missing_history_stops(self):
        a,b,r=self.data('slippage5');base=self.run_book(a,b,r,'slippage5')
        changed=deepcopy(b);changed['A'][a['session_dates'][1]]=dict(open='999',high='999',low='8',close='8')
        other=self.run_book(a,changed,r,'slippage5')
        self.assertEqual(base['provider_audit'][0],other['provider_audit'][0])
        def missing(**kwargs):
            value=r(**kwargs);value['histories']['A']['closes'].pop(0);return value
        self.assertEqual(self.run_book(a,b,missing,'slippage5')['status'],'BLOCKED')

    def test_callback_wait_without_target_date_migrates_latch_before_return(self):
        a,b,resolver=self.data('slippage5');a['close_prices']['B']=a['close_prices']['A']
        month=a['session_dates'][0]
        supplied=[dict(status='READY',target_shares={'A':7},target_decision_date=month,orders=[]),
            dict(status='READY',action='WAIT_POST_ACTION_MARK',target_shares={'B':14},orders=[],
                 target_adjustments=[dict(security_id='A',new_security_id='B',target_after=14)]),
            dict(status='READY',target_shares={'B':14},target_decision_date=month,orders=[])]
        calls=[]
        def resolved(**kwargs):
            value=resolver(**kwargs)
            for history in value['histories'].values():
                for close in history['closes'][:-1]:close['close']='100' if kwargs['decision_date']==month else '1'
            return value
        def drive(**kwargs):
            for index in range(3):
                calls.append(kwargs['order_provider'](decision_date=a['session_dates'][index],
                    active_date=a['session_dates'][index+1],state={'shares':{},'cash':'1000'}))
            return dict(status='COMPLETE',daily_ledger=[dict(date=a['session_dates'][3],equity='1000')])
        with patch.object(candidate,'build_cost_monthly_quantity_provider',return_value=lambda **kwargs:supplied.pop(0)), \
                patch.object(candidate,'run_next_open_book',side_effect=drive):
            self.run_book(a,b,resolved,'slippage5')
        self.assertEqual(calls[0]['target_shares'],{'A':3})
        self.assertEqual(calls[1]['action'],'WAIT_POST_ACTION_MARK')
        self.assertNotIn('target_decision_date',calls[1])
        self.assertEqual(calls[2]['target_shares'],{'B':7})
        self.assertEqual(calls[2]['risk_overlay']['monthly_latch']['latched_security_ids'],['B'])


if __name__=='__main__':unittest.main()
