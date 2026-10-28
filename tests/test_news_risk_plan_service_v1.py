"""Risk-plan callback publication barriers; injected services, no financial writes."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from datetime import timedelta
from copy import deepcopy

candidate = os.environ.get('NEWS_RISK_PLAN_STAGE_DIRECTORY')
if candidate:
    for name in ('news_risk_plan_v1', 'news_investment_service_v1'):
        specification = importlib.util.spec_from_file_location('data.' + name, Path(candidate) / (name + '.py'))
        loaded = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = loaded
        specification.loader.exec_module(loaded)
import test_news_investment_service_v1 as original_service_tests

class RiskPlanServiceTests(original_service_tests.ServiceTests):
    def provider(self, **arguments):
        self.provider_arguments = deepcopy(arguments)
        return dict(schema='NEWS_AI_RISK_PLAN_V1',status='READY',valid_until=(self.now+timedelta(seconds=30)).isoformat(),candidate_orders=[],executable=False)

    def test_callback_receives_postmodel_context_and_status_expiry(self):
        self.service.risk_plan_provider=self.provider
        result=self.run_job()
        self.assertEqual(result['status'],'COMPLETE',result)
        self.assertEqual(self.provider_arguments['original'],result['proposal']['original_preview'])
        self.assertEqual(self.provider_arguments['account'],self.account)
        self.assertFalse(result['proposal']['risk_plan']['executable'])
        self.now+=timedelta(seconds=31)
        self.assertEqual(self.service.status('j')['status'],'STALE')
        self.assertEqual(self.model.call_count,1)

    def test_callback_account_change_is_rejected(self):
        def change(**arguments):
            result=self.provider(**arguments)
            self.account['revision']='changed-during-new-quotes'
            return result
        self.service.risk_plan_provider=change
        result=self.run_job()
        self.assertEqual(result['status'],'STALE');self.assertNotIn('proposal',result)

    def test_callback_expired_quote_never_published(self):
        def expired(**arguments):
            result=self.provider(**arguments)
            result['valid_until']=self.now.isoformat()
            return result
        self.service.risk_plan_provider=expired
        result=self.run_job()
        self.assertEqual(result['status'],'FAILED');self.assertEqual(result['error'],'RISK_PLAN_EXPIRED')
        self.assertNotIn('proposal',result)

    def test_callback_total_deadline_and_futureclock_rejected(self):
        initial_now=self.now
        for shift in (361, -1):
            self.now=initial_now
            def delayed(**arguments):
                result=self.provider(**arguments)
                self.now+=timedelta(seconds=shift)
                return result
            self.service.risk_plan_provider=delayed
            result=self.run_job()
            self.assertEqual(result['status'],'FAILED')
            self.assertEqual(result['error'],'REVIEW_DEADLINE_EXCEEDED')
            self.assertNotIn('proposal',result)

    def test_blocking_final_context_cannot_cross_deadline(self):
        original_context=self.service.bound_context
        projected=[]
        def provider(**arguments):
            projected.append(True)
            return self.provider(**arguments)
        def context(binding):
            result=original_context(binding)
            if projected:
                self.now+=timedelta(seconds=361)
                projected.clear()
            return result
        self.service.risk_plan_provider=provider
        self.service.bound_context=context
        result=self.run_job()
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['error'],'REVIEW_DEADLINE_EXCEEDED')

    def test_missing_execution_evidence_is_explicit_wait(self):
        result=self.run_job()
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['proposal']['risk_plan']['status'],'WAIT')
        self.assertEqual(result['proposal']['risk_plan']['candidate_orders'],[])

if __name__ == '__main__':unittest.main()
