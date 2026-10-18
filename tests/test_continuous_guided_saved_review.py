from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import unittest
from scripts.review_continuous_guided_monthly_book import review_candidates,METHOD
from backtest.quantity_training_upper_bound import training_product_upper_bound,public_bound


class GuidedSavedReviewTests(unittest.TestCase):
    def fixture(self):
        root=Path(__file__).resolve().parents[1]
        prepared=json.loads((root/'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json').read_bytes())
        comparison=json.loads((root/'tmp/continuous_candidate_diagnostic_20261016_v1/2023-12-29.json').read_bytes())
        old=comparison['inherited_saved_result'];args=deepcopy(prepared['windows'][0]['search_arguments']);args['entered_cash']=old['entered_cash']
        result=dict(old,method_version=METHOD,selected=comparison['selected'],best_by_k=comparison['best_by_k'],continuous_comparison=comparison)
        result['training_objective_bound']=public_bound(training_product_upper_bound(cash=F(args['entered_cash']),fee=F(0),buffer=F(0),
            prices=args['prices'],scenarios=args['training_scenarios'],quantities=result['selected']['quantities']))
        return args,result

    def test_saved_candidates_exact_review_without_generation(self):
        args,result=self.fixture();checked=review_candidates(args,result)
        self.assertTrue(checked['strict_improvement']);self.assertEqual(checked['new_k'],2)

    def test_cash_trace_and_stale_bound_tamper_rejected(self):
        args,baseline=self.fixture()
        for case in ('cash','trace','bound'):
            result=deepcopy(baseline)
            if case=='cash':result['selected']['residual_cash']='999'
            elif case=='trace':result['continuous_comparison']['additional_generation']['trace'][0]['step']='1/2'
            else:result['training_objective_bound']['maximum_wealth_ratio_sum']='0'
            with self.subTest(case=case),self.assertRaises(ValueError):review_candidates(args,result)

    def test_stored_vertex_must_match_independent_exact_gradient(self):
        args,baseline=self.fixture()
        first=baseline['continuous_comparison']['additional_generation']['trace'][0]['vertex']
        alternate=next(s for s in args['prices']if s!=first)
        for replacement in (None,alternate):
            result=deepcopy(baseline)
            result['continuous_comparison']['additional_generation']['trace'][0]['vertex']=replacement
            with self.subTest(vertex=replacement),self.assertRaisesRegex(ValueError,'TRACE_GRADIENT_VERTEX_MISMATCH'):
                review_candidates(args,result)


if __name__=='__main__':unittest.main()
