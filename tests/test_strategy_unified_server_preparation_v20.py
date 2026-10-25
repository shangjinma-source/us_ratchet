"""Candidate integration checks; no source capture or account writes."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from fastapi import APIRouter
from data.strategy_unified_server_preparation_v20 import attach_daily_rss_v20

class CandidateMountTests(TestCase):
    def prepared(self):
        monthly=object();router=APIRouter()
        async def original():return {}
        router.add_api_route('/api/strategy-daily-v3/preview',original,methods=['POST'])
        router.add_api_route('/api/strategy-account',original,methods=['GET'])
        previous=SimpleNamespace(monthly=monthly,reader=object(),clock=object(),enabled=True,policy_id='policy')
        observed=SimpleNamespace(monthly=monthly,service=previous,journal=object(),clock=object(),policy_references={'release':'unchanged'})
        return dict(monthly=monthly,router=router,observed_daily=observed,validate_code=lambda:None)

    def test_replaces_only_preview_preserves_account_journal_and_validators(self):
        prepared=self.prepared();account_route=prepared['router'].routes[1];calls=[]
        prepared['validate_code']=lambda:calls.append('base')
        with patch('data.strategy_unified_server_preparation_v20.RollingDailyAdmissionV11') as daily, patch('data.strategy_unified_server_preparation_v20.ObservedDailyAdmission') as observed:
            result=attach_daily_rss_v20(prepared=prepared,validate_v20_sources=lambda:calls.append('new'))
            self.assertEqual(len(result['router'].routes),2)
            self.assertIs(result['router'].routes[0],account_route)
            self.assertEqual(sum(r.path=='/api/strategy-daily-v3/preview' for r in result['router'].routes),1)
            self.assertIs(daily.call_args.kwargs['monthly'],prepared['monthly'])
            self.assertIs(observed.call_args.kwargs['journal'],prepared['observed_daily'].journal)
            result['validate_code']()
            self.assertEqual(calls,['base','new']*3)

    def test_mismatched_account_service_rejected(self):
        prepared=self.prepared();prepared['observed_daily'].service.monthly=object()
        with self.assertRaisesRegex(ValueError,'V20_SHARED_MONTHLY_REQUIRED'):
            attach_daily_rss_v20(prepared=prepared,validate_v20_sources=lambda:None)

    def test_source_failure_prevents_mount(self):
        prepared=self.prepared()
        def fail():raise ValueError('CHANGED')
        with self.assertRaisesRegex(ValueError,'CHANGED'):
            attach_daily_rss_v20(prepared=prepared,validate_v20_sources=fail)
        self.assertEqual(len(prepared['router'].routes),2)
