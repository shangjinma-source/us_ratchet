from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from backtest import continuous_guided_account_decision as adapter
from backtest.quantity_training_upper_bound import training_product_upper_bound,public_bound


class GuidedAccountIndependentTests(unittest.TestCase):
    def test_new_target_recomputes_bound_and_does_not_inherit_old_certificate(self):
        args=dict(prices={'A':'10','B':'10'},metadata={'A':dict(ticker='A',issuer_id='a'),'B':dict(ticker='B',issuer_id='b')},
            entered_cash='100',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}],
            scenario_dates=['2026-01-15','2026-01-30'],decision_date='2026-01-30',max_objective_evaluations=100,fixed_seed='fixture')
        cash=dict(quantities={},actual_k=0,notional='0',fees='0',residual_cash='100',training_mean_net_log_wealth=0.0,
            training_gross_growth_product='1',exact_product_comparison=True,large_exact_product_serialization_omitted=False,
            actual_weights={},cash_fraction='1',issuer_unique=True,budget_conservation_exact=True)
        old=dict(method_version=adapter.BASE_VERSION,objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',status='BUDGET_STOPPED',
            decision_date=args['decision_date'],scenario_dates=args['scenario_dates'],max_objective_evaluations=100,entered_cash='100',
            fee_bps='0',minimum_cash_buffer='0',best_by_k={'0':cash},selected=cash,
            training_objective_bound={'sentinel':'OLD_BOUND'},objective_evaluations=1,global_optimum_established=False)
        before=deepcopy(old)
        with patch.object(adapter,'original_search',return_value=old) as original:
            result=adapter.enhanced_search(**args)
        self.assertEqual(original.call_count,1)
        self.assertEqual(old,before)
        self.assertEqual(result['selected']['actual_k'],2)
        expected=public_bound(training_product_upper_bound(cash=F(100),fee=F(0),buffer=F(0),prices=args['prices'],
            scenarios=args['training_scenarios'],quantities=result['selected']['quantities']))
        self.assertEqual(result['training_objective_bound'],expected)
        self.assertEqual(result['continuous_comparison']['inherited_saved_result']['training_objective_bound'],{'sentinel':'OLD_BOUND'})
        self.assertEqual(result['continuous_comparison']['additional_generation']['iterations_completed'],32)
        self.assertFalse(result['global_optimum_established'])


if __name__=='__main__':unittest.main()
