"""Injected service integration tests: no network, model process or real account."""
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from data.news_investment_service_v1 import NewsInvestmentService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=datetime(2026,10,27,15,1,tzinfo=timezone.utc)
        self.account=dict(revision='r',shares={'A':4},available_cash='100',cash_confirmation_valid=True,orders={})
        self.target=dict(target_id='t',proposal_id='p')
        self.binding=dict(expected_revision='r',target_id='t',expected_proposal_id='p')
        self.preview=dict(status='READY',account_revision='r',target_id='t',proposal_id='p',
            effective_target_quantities={'A':10},risk_valid_from='2026-10-27T15:00:00Z',risk_valid_until='2026-10-27T15:10:00Z',
            reference_quotes={'A':{'reference_valid_until':'2026-10-27T15:04:00Z'}})
        text='Official complete disclosure.';digest=sha256(text.encode()).hexdigest()
        self.source=dict(id='s',content_kind='FULL_TEXT',security_ids=['A'],text=text,text_sha256=digest,
            published_at='2026-10-27T14:00:00Z',observed_at='2026-10-27T14:01:00Z')
        self.answer=dict(status='SUCCEEDED',model='synthetic',rows=[dict(security_id='A',action='REDUCE_BUY',buy_fraction='1/2',reason='synthetic review',evidence=[dict(source_id='s',source_sha256=digest,quote=text)])])
        self.collector=Mock(return_value={'events':[]})
        self.builder=Mock(return_value={'sources':{'s':self.source},'coverage':[],'fingerprint':'f'})
        self.model=Mock(side_effect=lambda *a,**k:deepcopy(self.answer))
        self.preview_call=Mock(side_effect=lambda **k:deepcopy(self.preview))
        self.service=NewsInvestmentService(cache=Path(self.temp.name),context=lambda:(deepcopy(self.account),deepcopy(self.target),{'A':'AAA'}),
            preview=self.preview_call,collector=self.collector,source_builder=self.builder,model=self.model,clock=lambda:self.now)

    def run_job(self):
        job=dict(job_id='j',status='RUNNING',started_at=self.now.isoformat(),binding=self.binding)
        self.service.run(job)
        return self.service.status('j')

    def test_success_and_cached_requote_and_nonexecuting(self):
        for status in ('SUCCEEDED','CACHED'):
            self.answer['status']=status
            result=self.run_job()
            self.assertEqual(result['status'],'COMPLETE')
            proposal=result['proposal']
            self.assertEqual(proposal['rows'][0]['proposed_target_quantity'],7)
            self.assertFalse(proposal['executable'])
            self.assertEqual(proposal['review_valid_until'],'2026-10-27T15:04:00+00:00')
        self.assertEqual(self.preview_call.call_count,4)

    def test_published_original_preview_is_post_model_snapshot(self):
        initial = deepcopy(self.preview)
        def update_quote(*args, **kwargs):
            self.preview['reference_quotes']['A']['reference_valid_until'] = '2026-10-27T15:03:00Z'
            return deepcopy(self.answer)
        self.model.side_effect = update_quote
        result = self.run_job()
        self.assertEqual(result['status'], 'COMPLETE')
        proposal = result['proposal']
        self.assertNotEqual(proposal['original_preview'], initial)
        self.assertEqual(proposal['original_preview'], self.preview)
        from data.news_investment_service_v1 import digest
        self.assertEqual(proposal['original_preview_sha256'], digest(proposal['original_preview']))
        self.assertEqual(self.preview_call.call_count, 2)
        self.assertEqual(self.model.call_count, 1)

    def test_model_account_change_rejects(self):
        def change(*args,**kwargs):
            self.account['revision']='new'
            return self.answer
        self.model.side_effect=change
        result=self.run_job()
        self.assertEqual(result['status'],'STALE')
        with closing(self.service.connection()) as c:
            import json
            saved=json.loads(c.execute('SELECT document FROM jobs').fetchone()[0])
        self.assertEqual(saved['status'],'FAILED')
        self.assertNotIn('proposal',saved)

    def test_changed_target_after_model_rejected(self):
        def change(*args,**kwargs):
            self.preview['effective_target_quantities']['A']=0
            return self.answer
        self.model.side_effect=change
        self.assertEqual(self.run_job()['error'],'STRATEGY_TARGET_CHANGED_DURING_ANALYSIS')

    def test_expired_requote_and_risk_rejected(self):
        for kind in ('quote','risk'):
            def change(*args,**kwargs):
                if kind=='quote':self.preview['reference_quotes']['A']['reference_valid_until']=self.now.isoformat()
                else:self.preview['risk_valid_until']=self.now.isoformat()
                return self.answer
            self.model.side_effect=change
            self.assertEqual(self.run_job()['status'],'FAILED')
            self.preview['reference_quotes']['A']['reference_valid_until']='2026-10-27T15:04:00Z'

    def test_no_full_text_does_not_call_model(self):
        self.builder.return_value['sources']={}
        result=self.run_job()
        self.assertEqual(result['error'],'NO_COMPLETE_CURRENT_SOURCE_BODY')
        self.model.assert_not_called()

    def test_failure_and_wrong_domain_never_keep(self):
        self.answer['status']='FAILED'
        result=self.run_job();self.assertEqual(result['status'],'FAILED');self.assertNotIn('proposal',result)
        self.answer['status']='SUCCEEDED';self.answer['rows'][0]['security_id']='B'
        result=self.run_job();self.assertEqual(result['status'],'FAILED');self.assertNotIn('proposal',result)

    def test_status_expired_and_wrong_version(self):
        self.assertEqual(self.run_job()['status'],'COMPLETE')
        self.now+=timedelta(minutes=4)
        self.assertEqual(self.service.status('j')['status'],'STALE')
        self.now-=timedelta(minutes=4);self.target['proposal_id']='other'
        self.assertEqual(self.service.status('j')['status'],'STALE')

    def test_start_singleflight_then_cooldown(self):
        with patch('data.news_investment_service_v1.Thread') as thread, patch('data.news_investment_service_v1.owner_alive',return_value=True):
            code,job=self.service.start(self.binding)
            self.assertEqual(code,202);thread.return_value.start.assert_called_once()
            code,_=self.service.start(self.binding)
            self.assertEqual(code,409)
        with patch('data.news_investment_service_v1.owner_alive',return_value=False):
            code,result=self.service.start(self.binding)
            self.assertEqual(code,429);self.assertEqual(result['error'],'ONE_MINUTE_COOLDOWN')

    def test_news_generation_change_marks_completed_stale(self):
        with patch.object(self.service,'news_generation',return_value=1):
            self.assertEqual(self.run_job()['status'],'COMPLETE')
        with patch.object(self.service,'news_generation',return_value=2):
            self.assertEqual(self.service.status('j')['status'],'STALE')

    def test_news_generation_change_during_run_refuses_publication(self):
        with patch.object(self.service,'news_generation',side_effect=[1,2]):
            result=self.run_job()
        self.assertEqual(result['status'],'FAILED')
        self.assertNotIn('proposal',result)

    def test_deadline_expired_not_published(self):
        def slow(*args,**kwargs):
            self.now+=timedelta(seconds=361)
            return self.answer
        self.model.side_effect=slow
        result=self.run_job()
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['error'],'REVIEW_DEADLINE_EXCEEDED')
        self.assertNotIn('proposal',result)

    def test_uninitialized_account_has_no_financial_write_or_capture(self):
        self.service.context=lambda:(None,self.target,{})
        with self.assertRaises((ValueError,TypeError)):
            self.service.start(self.binding)
        self.assertFalse((Path(self.temp.name)/'investment_jobs_v1.sqlite3').exists())
        self.collector.assert_not_called();self.model.assert_not_called()

if __name__=='__main__':unittest.main()
