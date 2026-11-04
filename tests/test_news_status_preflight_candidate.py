from datetime import timedelta
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock
import test_news_investment_service_v1 as fixtures

path=Path(__file__).resolve().parents[1]/'docs/candidates/news_investment_service_status_preflight.py'
spec=importlib.util.spec_from_file_location('status_preflight',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class StatusPreflightTests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.ServiceTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.assertEqual(self.base.run_job()['status'],'COMPLETE')
        self.service=module.NewsInvestmentService.__new__(module.NewsInvestmentService)
        self.service.__dict__.update(self.base.service.__dict__)
        self.service.bound_context=Mock(wraps=self.service.bound_context)

    def test_expired_review_skips_context(self):
        self.base.now+=timedelta(minutes=4)
        self.assertEqual(self.service.status('j')['status'],'STALE')
        self.service.bound_context.assert_not_called()

    def test_changed_news_skips_context(self):
        self.service.news_generation=Mock(return_value=999)
        self.assertEqual(self.service.status('j')['status'],'STALE')
        self.service.bound_context.assert_not_called()

    def test_valid_review_still_checks_account(self):
        self.assertEqual(self.service.status('j')['status'],'COMPLETE')
        self.service.bound_context.assert_called_once()
        self.base.account['revision']='changed'
        self.assertEqual(self.service.status('j')['status'],'STALE')

    def test_expiry_during_context_still_rejected(self):
        original=self.service.bound_context
        def slow(binding):
            value=original(binding);self.base.now+=timedelta(minutes=4);return value
        self.service.bound_context=slow
        self.assertEqual(self.service.status('j')['status'],'STALE')

    def test_news_change_during_context_still_rejected(self):
        self.service.news_generation=Mock(side_effect=[0,1])
        self.assertEqual(self.service.status('j')['status'],'STALE')
        self.service.bound_context.assert_called_once()

if __name__=='__main__':unittest.main()
