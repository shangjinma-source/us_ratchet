import unittest
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction as F
from math import prod
from backtest.downside_candidate_observer_research import DownsideCandidateObserver
from scripts.audit_capped_training_frontier import evaluate


def fixture(a=None, b=None, reference=None, budget=20, limit=2):
    days = [(date(2020, 1, 1)+timedelta(days=i)).isoformat() for i in range(252)]
    a = a if a is not None else [F('-0.1'), F('0.2')]*126
    b = b if b is not None else [F('0.001')]*252
    reference = reference if reference is not None else [F('-0.01')]*252
    rows = {'A': dict(zip(days, a)), 'B': dict(zip(days, b))}
    args = dict(prices={'A':'10','B':'10'}, metadata={s:dict(issuer_id=s,ticker=s) for s in rows},
                entered_cash='100', fee_bps='0', minimum_cash_buffer='0',
                training_scenarios=[{s:prod(1+x for x in list(r.values())[i*21:(i+1)*21]) for s,r in rows.items()} for i in range(12)],
                scenario_dates=days[20::21],decision_date=days[-1])
    kwargs = dict(max_holdings=limit, search_arguments=args, stock_returns=rows,
                  qqq_reference=dict(zip(days,reference)),max_risk_evaluations=budget)
    return kwargs


def finish(observer):
    observer.end_observation()
    return observer.finalize()


class ObserverTests(unittest.TestCase):
    def test_second_growth_place_survives_and_inputs_unchanged(self):
        kwargs=fixture(); original=deepcopy(kwargs); observer=DownsideCandidateObserver(**kwargs)
        self.assertGreater(evaluate({'A':5},kwargs['search_arguments'])['product'],evaluate({'B':5},kwargs['search_arguments'])['product'])
        for i,q in enumerate(({}, {'A':5},{'B':5})):
            observer.observe(q,phase='base',evaluation_index=i)
        result=finish(observer)
        self.assertEqual(result['eligible_best_by_k']['1']['target_quantities'],{'B':5})
        self.assertIsNotNone(result['cash']);self.assertEqual(kwargs,original)
        result['eligible_best_by_k']['1']['target_quantities']['B']=0
        self.assertEqual(observer.finalize()['eligible_best_by_k']['1']['target_quantities'],{'B':5})

    def test_cap_rank_reversal(self):
        kwargs=fixture(a=[F('0.001')]*252,b=[F('0.0018')]*252)
        args=kwargs['search_arguments']
        self.assertGreater(evaluate({'A':10},args)['product'],evaluate({'B':4},args)['product'])
        observer=DownsideCandidateObserver(**kwargs)
        observer.observe({'A':10},phase='base',evaluation_index=0)
        observer.observe({'B':4},phase='continuous',evaluation_index=1)
        self.assertEqual(finish(observer)['eligible_best_by_k']['1']['target_quantities'],{'B':4})

    def test_raw_and_capped_cross_phase_dedup(self):
        observer=DownsideCandidateObserver(**fixture())
        for i,q in enumerate(({'B':10},{'B':10},{'B':9},{'A':0,'B':9})):
            observer.observe(q,phase=str(i),evaluation_index=i)
        result=finish(observer)
        self.assertEqual(result['coverage']['raw_unique_observed'],2)
        self.assertEqual(result['coverage']['risk_evaluated'],1)

    def test_exact_boundary_and_just_over(self):
        value=F(-1,3)
        observer=DownsideCandidateObserver(**fixture(a=[value]*252,reference=[value/2]*252))
        observer.observe({'A':5},phase='base',evaluation_index=0)
        result=finish(observer)
        self.assertTrue(result['eligible_best_by_k']['1']['exact_boundary_comparison'])
        observer=DownsideCandidateObserver(**fixture(a=[value-F(1,10**90)]*252,reference=[value/2]*252))
        observer.observe({'A':5},phase='base',evaluation_index=0)
        self.assertEqual(finish(observer)['eligible_best_by_k'],{})

    def test_only_cash_and_limit(self):
        observer=DownsideCandidateObserver(**fixture(a=[F('-0.2')]*252,b=[F('-0.2')]*252,limit=1))
        for i,q in enumerate(({}, {'A':5},{'B':5},{'A':4,'B':4})):
            observer.observe(q,phase='base',evaluation_index=i)
        result=finish(observer)
        self.assertEqual(result['eligible_best_by_k'],{})
        self.assertEqual(result['coverage']['risk_pass_cash'],1)
        self.assertEqual(result['coverage']['over_holdings_limit'],1)

    def test_budget_and_stream_must_be_complete(self):
        observer=DownsideCandidateObserver(**fixture(budget=1))
        with self.assertRaisesRegex(ValueError,'NOT_ENDED'):observer.finalize()
        observer.observe({},phase='base',evaluation_index=0)
        observer.observe({'B':5},phase='base',evaluation_index=1)
        observer.end_observation()
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):observer.finalize()
        with self.assertRaisesRegex(ValueError,'ALREADY_ENDED'):observer.observe({},phase='base',evaluation_index=2)

    def test_raw_invalid_cannot_be_laundered(self):
        for q in ({'A':True},{'A':-1},{'A':1.5},{'X':1},{'A':11}):
            with self.subTest(q=q):
                observer=DownsideCandidateObserver(**fixture())
                with self.assertRaises(ValueError):observer.observe(q,phase='base',evaluation_index=0)
        kwargs=fixture();kwargs['search_arguments']['metadata']['B']['issuer_id']='A'
        observer=DownsideCandidateObserver(**kwargs)
        with self.assertRaisesRegex(ValueError,'Duplicate issuer'):observer.observe({'A':1,'B':1},phase='base',evaluation_index=0)

    def test_exception_poisons_finalize_and_cash_is_always_present(self):
        observer=DownsideCandidateObserver(**fixture())
        with self.assertRaises(ValueError):observer.observe({'A':True},phase='base',evaluation_index=0)
        observer.end_observation()
        with self.assertRaisesRegex(ValueError,'OBSERVATION_FAILED'):observer.finalize()
        observer=DownsideCandidateObserver(**fixture())
        observer.observe({'A':5},phase='base',evaluation_index=0)
        result=finish(observer)
        self.assertEqual(result['eligible_best_by_k'],{})
        self.assertEqual(result['cash']['target_quantities'],{})
        self.assertEqual(result['coverage']['raw_unique_observed'],1)
        self.assertEqual(result['coverage']['risk_pass_cash'],0)
        self.assertFalse(result['search_coverage_verified'])

    def test_duplicate_does_not_repeat_score(self):
        from unittest.mock import patch
        import backtest.downside_candidate_observer_research as module
        observer=DownsideCandidateObserver(**fixture())
        observer.observe({'B':5},phase='base',evaluation_index=0)
        with patch.object(module,'evaluate',side_effect=AssertionError('duplicate rescored')):
            observer.observe({'B':5},phase='continuous',evaluation_index=1)
        finish(observer)

    def test_bad_dates_domain_and_scenario_rejected(self):
        kwargs=fixture();kwargs['stock_returns']['A'].pop(next(iter(kwargs['stock_returns']['A'])))
        with self.assertRaises(ValueError):DownsideCandidateObserver(**kwargs)
        kwargs=fixture();kwargs['stock_returns'].pop('A')
        with self.assertRaises(ValueError):DownsideCandidateObserver(**kwargs)
        kwargs=fixture();kwargs['search_arguments']['training_scenarios'][0]['A']=F(2)
        with self.assertRaisesRegex(ValueError,'COORDINATE'):DownsideCandidateObserver(**kwargs)


if __name__=='__main__':unittest.main()
