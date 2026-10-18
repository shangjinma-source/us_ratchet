import importlib.util
from pathlib import Path
import unittest

import pandas as pd

from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from test_ndx_joint_weight_evaluation import fixture

spec=importlib.util.spec_from_file_location('probe',Path(__file__).resolve().parents[1]/'scripts/ndx_whole_lot_failure_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class WholeLotFailureProbeTests(unittest.TestCase):
    def test_real_observer_does_not_change_v2_result_or_dependency(self):
        task,inputs=fixture()
        dependency=probe.evaluator._PORTFOLIO.__globals__['simulate_continuous_whole_lot_rebalance']
        result=probe.evaluate_observed(task,inputs)
        self.assertTrue(result['observer_result_exactly_unchanged'])
        self.assertIs(dependency,probe.evaluator._PORTFOLIO.__globals__['simulate_continuous_whole_lot_rebalance'])
        self.assertEqual(result['observation']['original_summary']['whole_lot_rebalance_trace_sha256'],
            result['result']['whole_lot_rebalance_trace_sha256'])
        self.assertTrue(result['observation']['attribution']['daily'])

    def test_daily_weight_floor_drift_separate_from_rebalance(self):
        dates=pd.date_range('2020-01-01',periods=2)
        prices=pd.DataFrame({'A':[10.,1.],'B':[10.,10.],'C':[10.,10.],'D':[10.,10.]},index=dates)
        schedule=[(dates[0],{t:.25 for t in prices})]
        contract=dict(risk_chain_by_ticker={t:t for t in prices},portfolio_cash_usd=100.,
            minimum_cash_buffer_usd=0.,transaction_cost_bps=0.,max_single_weight=1.,min_single_weight=.2,
            top_weight_cap=1.,minimum_effective_n_ratio=.5,risk_chain_top1_cap=1.)
        summary,ledger=simulate_continuous_whole_lot_rebalance(prices,schedule,**contract)
        before=ledger.copy(deep=True)
        report=probe.explain_path(prices,schedule,ledger,contract)
        self.assertEqual(report['daily'][0]['failures'],[])
        self.assertEqual(report['first_failure']['date'],'2020-01-02')
        self.assertEqual(report['failure_summary']['WEIGHT_FLOOR']['rebalance_days'],0)
        self.assertEqual(report['failure_summary']['WEIGHT_FLOOR']['holding_days'],1)
        self.assertEqual(report['failure_summary']['WEIGHT_FLOOR']['new_holding_drift_breaches'],1)
        self.assertFalse(summary['whole_lot_constraints_preserved_all_days'])
        pd.testing.assert_frame_equal(ledger,before,check_exact=True)

    def test_rounding_min_share_failure_is_rebalance_not_drift(self):
        dates=pd.date_range('2020-01-01',periods=1)
        prices=pd.DataFrame({'A':[1000.],'B':[1000.]},index=dates)
        schedule=[(dates[0],{'A':.5,'B':.5})]
        contract=dict(risk_chain_by_ticker={'A':'A','B':'B'},portfolio_cash_usd=100.,
            minimum_cash_buffer_usd=0.,transaction_cost_bps=0.,max_single_weight=1.,min_single_weight=.1,
            top_weight_cap=1.,minimum_effective_n_ratio=.5,risk_chain_top1_cap=1.)
        _,ledger=simulate_continuous_whole_lot_rebalance(prices,schedule,**contract)
        report=probe.explain_path(prices,schedule,ledger,contract)
        self.assertIn('MINIMUM_ONE_SHARE',report['first_failure']['failures'])
        self.assertEqual(report['first_failure']['phase'],'REBALANCE_DAY')
        self.assertEqual(len(report['independent_window_min_share_failures']),1)


if __name__=='__main__':
    unittest.main()
