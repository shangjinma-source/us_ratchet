from copy import deepcopy
import unittest
from backtest.ma9_sma20_half import ma9_sma20_half_target
from backtest.continuous_guided_ma9_sma20_half_next_open import run_cost_ma9_sma20_half_next_open
from backtest.continuous_guided_cost_stress import prepare_arm, SCENARIOS, run_cost_stress_arm
from test_current_quantity_v2_risk_overlays import fixture
import test_continuous_guided_cost_stress as cost


class DualAverageTests(unittest.TestCase):
    def test_above20_below9_and_equality(self):
        for values,expected in [([1]*11+[20]*8+[10],3),([10]*20,3),([1]*19+[10],7),([20]*11+[1]*8+[10],3)]:
            args=fixture({'A':values},quantities={'A':7});saved=deepcopy(args)
            r=ma9_sma20_half_target(**args)
            self.assertEqual(r['target_quantities']['A'],expected)
            self.assertEqual(args,saved)
            self.assertEqual(ma9_sma20_half_target(**args)['target_quantities']['A'],expected)

    def test_missing_future_or_wrong_unit_rejected(self):
        for fault in ('missing','future','unit'):
            x=fixture({'A':[1]*19+[10]},quantities={'A':7})
            if fault=='missing':x['histories']['A']['closes'].pop()
            if fault=='future':x['histories']['A']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
            if fault=='unit':x['base_target']['price_units']['A']='wrong'
            with self.assertRaises(ValueError):ma9_sma20_half_target(**x)

    def test_real_book_all_on_equal_baseline_both_costs(self):
        a,b,resolver=cost.CostStressTests().data()
        def strong(**kwargs):
            x=resolver(**kwargs)
            for h in x['histories'].values():
                for row in h['closes'][:-1]:row['close']='1'
            return x
        for scenario in SCENARIOS:
            r=run_cost_ma9_sma20_half_next_open(assembled=prepare_arm(a,scenario),ohlc=b,initial_cash='1000',history_resolver=strong,**SCENARIOS[scenario])
            old=run_cost_stress_arm(arm='continuous32_half',scenario=scenario,assembled=a,ohlc=b,initial_cash='1000',history_resolver=strong)
            self.assertEqual(r['status'],'COMPLETE')
            self.assertEqual(r['daily_ledger'],old['daily_ledger'])
            self.assertEqual(r['selection_account_states'],old['selection_account_states'])

    def test_invalid_history_stops_before_any_fill(self):
        a,b,resolver=cost.CostStressTests().data()
        def broken(**kwargs):
            x=resolver(**kwargs);x['histories']['A']['closes'].pop(0);return x
        r=run_cost_ma9_sma20_half_next_open(assembled=prepare_arm(a,'slippage5'),ohlc=b,initial_cash='1000',history_resolver=broken,**SCENARIOS['slippage5'])
        self.assertEqual(r['status'],'BLOCKED')
        self.assertFalse(any(x['event']=='ASSUMED_NEXT_OPEN_FILLED' for x in r['order_log']))

if __name__=='__main__':unittest.main()
