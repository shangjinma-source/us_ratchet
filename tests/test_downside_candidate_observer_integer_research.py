"""Reuse original boundary cases plus exact whole-search sidecar comparison."""
import unittest
from unittest.mock import patch
import test_downside_candidate_observer_research as original_tests
from test_downside_observed_search import fixture, observed
from backtest.downside_candidate_observer_research import DownsideCandidateObserver as Original
from backtest.downside_candidate_observer_integer_research import DownsideCandidateObserver as Candidate
import backtest.downside_candidate_observer_integer_research as candidate_module


class IntegerBoundaryTests(original_tests.ObserverTests):
    def setUp(self):
        substitute=patch.object(original_tests,'DownsideCandidateObserver',Candidate)
        substitute.start();self.addCleanup(substitute.stop)

    def test_duplicate_does_not_repeat_score(self):
        observer=Candidate(**original_tests.fixture())
        observer.observe({'B':5},phase='base',evaluation_index=0)
        with patch.object(candidate_module,'evaluate',side_effect=AssertionError('duplicate rescored')):
            observer.observe({'B':5},phase='continuous',evaluation_index=1)
        original_tests.finish(observer)


class IntegerIntegrationTests(unittest.TestCase):
    def test_two_phase_search_and_entire_sidecar_equal(self):
        args,kwargs=fixture();first=Original(**kwargs);second=Candidate(**kwargs)
        a=observed(candidate_observer=first,**args);b=observed(candidate_observer=second,**args)
        first.end_observation();second.end_observation()
        self.assertEqual(a,b);self.assertEqual(first.finalize(),second.finalize())
        self.assertEqual(first.raw_seen,second.raw_seen);self.assertEqual(first.cap_seen,second.cap_seen)

    def test_budget_and_failure_state_equal(self):
        args,kwargs=fixture();kwargs['max_risk_evaluations']=1
        first=Original(**kwargs);second=Candidate(**kwargs)
        self.assertEqual(observed(candidate_observer=first,**args),observed(candidate_observer=second,**args))
        self.assertEqual(first.counts,second.counts)
        for observer in (first,second):
            observer.end_observation()
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_RISK'):observer.finalize()
        for cls in (Original,Candidate):
            observer=cls(**kwargs)
            with self.assertRaisesRegex(ValueError,'INVALID_RAW'):observer.observe({'A':True},phase='base',evaluation_index=0)
            observer.end_observation()
            with self.assertRaisesRegex(ValueError,'OBSERVATION_FAILED'):observer.finalize()
            self.assertTrue(observer.failed);self.assertFalse(observer.complete)


if __name__=='__main__':unittest.main()
