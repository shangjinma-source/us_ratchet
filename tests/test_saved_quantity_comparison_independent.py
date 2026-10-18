from copy import deepcopy
from fractions import Fraction as F
import math
import unittest
from backtest.saved_quantity_candidate_comparison import compare_saved_candidates,canonical_sha256


class IndependentSavedComparisonTests(unittest.TestCase):
    def fixture(self,gross='2'):
        args=dict(prices={'A':'10','B':'10'},metadata={'A':dict(ticker='A',issuer_id='a'),'B':dict(ticker='B',issuer_id='b')},
            entered_cash='100',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':gross,'B':gross}],
            scenario_dates=['2026-01-30'],decision_date='2026-01-30',max_objective_evaluations=100,fixed_seed='fixture')
        def record(q):
            n=10*sum(q.values());r=100-n;g=(F(r)+n*F(gross))/100
            return dict(quantities=q,actual_k=len(q),notional=str(n),fees='0',residual_cash=str(r),
                training_mean_net_log_wealth=math.log(g.numerator)-math.log(g.denominator),training_gross_growth_product=str(g),
                exact_product_comparison=True,large_exact_product_serialization_omitted=False,
                actual_weights={s:str(F(v,10))for s,v in q.items()},cash_fraction=str(F(r,100)),issuer_unique=True,budget_conservation_exact=True)
        best={'0':record({}),'1':record({'B':10}),'2':record({'A':5,'B':5})}
        old=dict(method_version='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',
            status='BUDGET_STOPPED',decision_date=args['decision_date'],scenario_dates=args['scenario_dates'],max_objective_evaluations=100,
            entered_cash='100',fee_bps='0',minimum_cash_buffer='0',best_by_k=best,selected=best['0' if gross=='1' else '1'],
            per_k=[dict(k=2,visited_states=1)],global_optimum_established=False)
        return args,old

    def compare(self,args,old):
        return compare_saved_candidates(search_arguments=args,saved_result=old,iterations=4,
            expected_search_arguments_sha256=canonical_sha256(args),expected_saved_result_sha256=canonical_sha256(old))

    def test_legacy_lexicographically_larger_tie_retained(self):
        args,old=self.fixture();before=deepcopy((args,old));result=self.compare(args,old)
        self.assertEqual(result['selected']['quantities'],{'B':10})
        self.assertEqual(result['inherited_saved_result'],old)
        self.assertEqual(result['best_by_k']['2'],old['best_by_k']['2'])
        self.assertEqual((args,old),before)
        self.assertEqual(result['exact_evaluations'],dict(saved_unique=3,new_unique=1))
        self.assertFalse(result['inherited_coverage_reverified'])

    def test_lower_notional_tie_keeps_all_cash(self):
        args,old=self.fixture('1');result=self.compare(args,old)
        self.assertEqual(result['selected']['quantities'],{})
        self.assertEqual(result['exact_evaluations']['new_unique'],0)

    def test_saved_selected_not_frontier_winner_and_pins_reject(self):
        args,old=self.fixture();old['selected']=old['best_by_k']['0']
        with self.assertRaisesRegex(ValueError,'SAVED_SELECTION'):self.compare(args,old)
        args,old=self.fixture();h=canonical_sha256(args);args['prices']['A']='11'
        with self.assertRaisesRegex(ValueError,'CALLER_SAVED_BINDING'):
            compare_saved_candidates(search_arguments=args,saved_result=old,iterations=4,
                expected_search_arguments_sha256=h,expected_saved_result_sha256=canonical_sha256(old))


if __name__=='__main__':unittest.main()
