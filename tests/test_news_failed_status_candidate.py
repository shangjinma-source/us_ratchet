"""Terminal failures do not acquire financial context; COMPLETE remains bound."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock,patch
from contextlib import closing
import unittest
import test_news_investment_service_v1 as prior

path=Path(__file__).resolve().parents[1]/'docs/candidates/news_investment_service_failed_status.py'
spec=importlib.util.spec_from_file_location('failed_status_candidate',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Tests(prior.ServiceTests):
    def setUp(self):
        with patch.object(prior,'NewsInvestmentService',module.NewsInvestmentService):super().setUp()

    def test_start_singleflight_then_cooldown(self):
        with patch.object(module,'Thread') as thread, patch.object(module,'owner_alive',return_value=True):
            code,job=self.service.start(self.binding)
            self.assertEqual(code,202);thread.return_value.start.assert_called_once()
            self.assertEqual(self.service.start(self.binding)[0],409)
        with patch.object(module,'owner_alive',return_value=False):
            code,result=self.service.start(self.binding)
            self.assertEqual(code,429);self.assertEqual(result['error'],'ONE_MINUTE_COOLDOWN')

    def test_model_account_change_rejects(self):
        def change(*args,**kwargs):
            self.account['revision']='new';return self.answer
        self.model.side_effect=change
        result=self.run_job()
        self.assertEqual(result['status'],'FAILED');self.assertNotIn('proposal',result)
        self.assertEqual(result['error'],'STALE_ACCOUNT_OR_TARGET')

    def test_failed_never_calls_context_or_guards_and_never_leaks_proposal(self):
        failed=dict(job_id='j',status='FAILED',started_at=self.now.isoformat(),finished_at=self.now.isoformat(),error='STALE_ACCOUNT_OR_TARGET',binding=self.binding,proposal={'secret':'old opinion'},event_pending={'secret':'old event'},stage_timings={'model':12})
        with closing(self.service.connection()) as c,c:self.service.save(c,failed)
        # These call sites would block in production. A raising sentinel proves
        # they are not entered, without introducing a hanging test thread.
        for name in ('bound_context','validate_event_control','news_generation','background_guard'):
            setattr(self.service,name,Mock(side_effect=AssertionError('must not enter '+name)))
        result=self.service.status('j')
        self.assertEqual(result, {k:failed[k] for k in ('job_id','status','started_at','finished_at','error','stage_timings')})
        for name in ('bound_context','validate_event_control','news_generation','background_guard'):getattr(self.service,name).assert_not_called()

    def test_complete_stale_binding_still_rejected(self):
        self.assertEqual(self.run_job()['status'],'COMPLETE')
        self.account['revision']='changed'
        result=self.service.status('j')
        self.assertEqual(result['status'],'STALE');self.assertNotIn('proposal',result)

if __name__=='__main__':unittest.main()
