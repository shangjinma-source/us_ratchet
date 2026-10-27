"""Production service budget tests with isolated fixtures; no network."""
import runpy
from pathlib import Path
from datetime import timedelta
import unittest

ROOT=Path(__file__).resolve().parents[1]
Candidate=runpy.run_path(str(ROOT/'data/news_investment_service_v1.py'))['NewsInvestmentService']

class PreModelDeadlineTests(unittest.TestCase):
    def fixture(self):
        fixture_class=runpy.run_path(str(ROOT/'tests/test_news_investment_service_v1.py'))['ServiceTests']
        base=fixture_class();base.setUp();self.addCleanup(base.doCleanups)
        base.service.__class__=Candidate
        return base

    def test_exhausted_budget_does_not_start_model(self):
        for seconds in (360,361):
            with self.subTest(seconds=seconds):
                base=self.fixture()
                def capture(*args,**kwargs):
                    base.now+=timedelta(seconds=seconds)
                    return {'events':[]}
                base.collector.side_effect=capture
                result=base.run_job()
                self.assertEqual(result['status'],'FAILED')
                self.assertEqual(result['error'],'REVIEW_DEADLINE_EXCEEDED')
                base.model.assert_not_called()

    def test_thirty_seconds_remaining_caps_model_timeout(self):
        base=self.fixture()
        def capture(*args,**kwargs):
            base.now+=timedelta(seconds=330)
            return {'events':[]}
        base.collector.side_effect=capture
        base.run_job()
        self.assertEqual(base.model.call_count,1)
        self.assertEqual(base.model.call_args.kwargs['timeout'],30)

if __name__=='__main__':unittest.main()
