from copy import deepcopy
import unittest
from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities
from backtest.saved_quantity_candidate_comparison import compare_saved_candidates, canonical_sha256


class SavedComparisonTests(unittest.TestCase):
    def fixture(self):
        args=dict(prices={'A':'10','B':'10'},metadata={'A':dict(ticker='AAA',issuer_id='a'),'B':dict(ticker='BBB',issuer_id='b')},
            entered_cash='100',fee_bps=0,minimum_cash_buffer=0,
            training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}],scenario_dates=['2026-01-01','2026-02-01'],
            decision_date='2026-02-02',max_objective_evaluations=32,fixed_seed='synthetic')
        return args,search_fresh_cash_quantities(**args)

    def compare(self,args,old):
        return compare_saved_candidates(search_arguments=args,saved_result=old,iterations=12,
            expected_search_arguments_sha256=canonical_sha256(args),expected_saved_result_sha256=canonical_sha256(old))

    def test_exact_frontier_retained_and_no_mutation(self):
        args,old=self.fixture();original=deepcopy((args,old));result=self.compare(args,old)
        self.assertEqual((args,old),original);self.assertEqual(result['inherited_saved_result'],old)
        self.assertTrue(set(old['best_by_k']).issubset(result['best_by_k']))
        self.assertTrue(result['selected_training_objective_not_lower'])
        self.assertFalse(result['equal_computation_budget_comparison']);self.assertFalse(result['inherited_coverage_reverified'])

    def test_rehashed_false_records_and_context_rejected(self):
        for field,value in [('residual_cash','999'),('fees','9'),('actual_weights',{'A':'1'}),('training_mean_net_log_wealth',99),('actual_k',99)]:
            args,old=self.fixture();old['selected'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.compare(args,old)
        for field,value in [('entered_cash','101'),('decision_date','2026-02-03'),('scenario_dates',['2026-01-02','2026-02-01'])]:
            args,old=self.fixture();args[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.compare(args,old)
        args,old=self.fixture();old['best_by_k']['2']['quantities']={'A':True,'B':1}
        with self.assertRaises(ValueError):self.compare(args,old)

    def test_caller_pins_and_issuer_and_future_reject(self):
        args,old=self.fixture()
        with self.assertRaisesRegex(ValueError,'CALLER_SAVED_BINDING_MISMATCH'):
            compare_saved_candidates(search_arguments=args,saved_result=old,iterations=12,
                expected_search_arguments_sha256='a'*64,expected_saved_result_sha256=canonical_sha256(old))
        args['metadata']['B']['issuer_id']='a'
        with self.assertRaisesRegex(ValueError,'ISSUER_CONFLICT'):self.compare(args,old)
        args,old=self.fixture();args['scenario_dates'][-1]='2099-01-01'
        with self.assertRaises(ValueError):self.compare(args,old)


if __name__=='__main__':unittest.main()
