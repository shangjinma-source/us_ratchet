from copy import deepcopy
from fractions import Fraction
import unittest
from backtest.weak_trend_no_add import no_add_target
from backtest.continuous_guided_weak_no_add_next_open import run_cost_weak_no_add_next_open
from backtest.continuous_guided_cost_stress import prepare_arm, SCENARIOS, run_cost_stress_arm
import test_continuous_guided_cost_stress as fixtures
import test_monthly_latched_half_actions_integration as action_fixtures


def risk(ceiling=7, on=False):
    return dict(target_quantities={'A':ceiling}, diagnostics={'A':dict(monthly_ceiling=ceiling,on=on)})


class NoAddTests(unittest.TestCase):
    def test_zero_odd_and_no_compounding(self):
        self.assertEqual(no_add_target(risk=risk(),shares={})['target_quantities'],{'A':0})
        first=no_add_target(risk=risk(),shares={'A':7})['target_quantities']
        self.assertEqual(first,{'A':3})
        self.assertEqual(no_add_target(risk=risk(),shares=first)['target_quantities'],first)
        self.assertEqual(no_add_target(risk=risk(19),shares=first)['target_quantities'],first)
        self.assertEqual(no_add_target(risk=risk(19,True),shares=first)['target_quantities'],{'A':19})

    def test_carried_pending_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError,'CARRIED_PENDING'):
            no_add_target(risk=risk(),shares={},pending_orders=[{'side':'BUY','quantity':3}])

    def run_book(self,a,b,r,scenario='slippage5'):
        return run_cost_weak_no_add_next_open(assembled=prepare_arm(a,scenario),ohlc=b,
            history_resolver=r,initial_cash='1000',**SCENARIOS[scenario])

    def test_real_weak_initial_zero_and_recovery(self):
        a,b,r=fixtures.CostStressTests().data()
        def history(**kw):
            x=r(**kw)
            for h in x['histories'].values():
                for row in h['closes'][:-1]:row['close']='100' if kw['decision_date']==a['session_dates'][0] else '1'
            return x
        out=self.run_book(a,b,history)
        self.assertEqual(out['status'],'COMPLETE')
        self.assertEqual(out['provider_audit'][0]['orders'],[])
        self.assertEqual(out['provider_audit'][0]['target_shares'],{'A':0})
        self.assertTrue(any(x['side']=='BUY' for x in out['provider_audit'][1]['orders']))
        self.assertTrue(all(Fraction(x['cash'])>=0 for x in out['daily_ledger']))

    def test_strong_matches_sealed_full_and_bad_history_blocks(self):
        a,b,r=fixtures.CostStressTests().data()
        def strong(**kw):
            x=r(**kw)
            for h in x['histories'].values():
                for row in h['closes'][:-1]:row['close']='1'
            return x
        for s in SCENARIOS:
            out=self.run_book(a,b,strong,s)
            full=run_cost_stress_arm(arm='continuous32',scenario=s,assembled=a,ohlc=b,initial_cash='1000')
            self.assertEqual(out['daily_ledger'],full['daily_ledger'])
        def future(**kw):
            x=strong(**kw)
            x['histories']['A']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
            return x
        self.assertEqual(self.run_book(a,b,future)['status'],'BLOCKED')

    def test_real_identity_split_uses_adjusted_holdings_and_full_ceiling(self):
        a,b,original,calls=action_fixtures.MonthlyLatchedHalfActionsIntegrationTests().fixture();days=a['session_dates']
        b['A'][days[1]].update(open='9',high='40')
        def history(**kw):
            x=original(**kw)
            for h in x['histories'].values():
                for row in h['closes'][:-1]:row['close']='1' if kw['decision_date']==days[0] else '100'
            return x
        action=dict(date=days[2],security_id='A',new_security_id='B',type='split_identity',old_shares=1,new_shares=2,source_references=['official'])
        a['actions']=[deepcopy(action)];a['provider_actions']=[deepcopy(action)]
        out=self.run_book(a,b,history)
        self.assertEqual(out['status'],'COMPLETE')
        self.assertTrue(any(x['event']=='SPLIT_QUANTITY_AND_MARK_ADJUSTED' for x in out['order_log']))
        initial=out['provider_audit'][0]['monthly_ceiling']['A']
        for row in out['provider_audit'][2:]:
            self.assertEqual(row['monthly_ceiling'],{'B':initial*2})
            d=row['risk_overlay']['diagnostics']['B']
            self.assertEqual(row['target_shares']['B'],min(initial,d['no_add_current_shares']))
            self.assertFalse(any(x['side']=='BUY' for x in row['orders']))

if __name__=='__main__':unittest.main()
