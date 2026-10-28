"""Injected reference-bound service integration; no network or model process."""
from copy import deepcopy
from unittest.mock import Mock, patch
import unittest
import test_news_investment_service_v1 as existing
from data.news_investment_reference_service_v1 import NewsInvestmentReferenceService, KEY


class ReferenceServiceTests(unittest.TestCase):
    def setUp(self):
        self.base=existing.ServiceTests();self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.account['account_id']='a'
        self.ref=dict(account_id='a',reference_version=1,reference_state_sha256='a'*64,configuration_sha256='c'*64)
        self.base.preview.update(policy_id='SAVED_FRONTIER_CAP50_EXIT20_REENTRY_V1',reference_projection=deepcopy(self.ref))
        old=self.base.service
        self.plan=Mock(return_value={'status':'WAIT','reason':'synthetic no quotes'})
        self.service=NewsInvestmentReferenceService(reference_reader=lambda:deepcopy(self.ref),
            cache=old.cache,context=old.context,preview=self.base.preview_call,
            collector=self.base.collector,source_builder=self.base.builder,model=self.base.model,
            clock=old.clock,risk_plan_provider=self.plan)
        self.binding=dict(self.base.binding,**{KEY:deepcopy(self.ref)})

    def run_job(self, **extra):
        job=dict(job_id='j',status='RUNNING',started_at=self.base.now.isoformat(),binding=deepcopy(self.binding),**extra)
        self.service.run(job)
        return self.service.status('j')

    def test_complete_then_same_request_ids_lock_change_stales(self):
        self.assertEqual(self.run_job()['status'],'COMPLETE')
        self.ref['reference_version']+=1
        self.assertEqual(self.service.status('j')['status'],'STALE')
        self.assertNotIn('proposal',self.service.status('j'))
        self.assertNotIn(KEY,self.base.preview_call.call_args.kwargs)

    def test_change_during_model_discards_answer(self):
        def change(*args,**kwargs):
            self.ref['reference_state_sha256']='b'*64
            return deepcopy(self.base.answer)
        self.base.model.side_effect=change
        self.assertEqual(self.run_job()['status'],'STALE')
        self.plan.assert_not_called()

    def test_change_during_risk_bridge_discards_result(self):
        def change(**kwargs):
            self.ref['configuration_sha256']='d'*64
            return {'status':'WAIT'}
        self.plan.side_effect=change
        self.assertEqual(self.run_job()['status'],'STALE')

    def test_risk_bridge_cannot_increase_filtered_target(self):
        self.plan.return_value={'status':'READY','rows':[{'security_id':'A','planned_target_quantity':11}], 'candidate_orders':[]}
        result=self.run_job()
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['error'],'AI_CANNOT_RELEASE_REFERENCE_BUY_LOCK')

    def test_missing_old_binding_and_pre_run_changes_do_not_call_model(self):
        self.binding.pop(KEY)
        self.assertEqual(self.run_job()['status'],'STALE')
        self.base.model.assert_not_called()

    def test_event_pending_change_checks_before_source_analysis(self):
        self.service.event_guard=lambda pending:True
        pending={'execution_window':{'not_before':'2026-10-27T15:00:00Z'},'opinion_valid_until':'2026-10-27T15:05:00Z'}
        self.ref['reference_version']+=1
        self.assertEqual(self.run_job(event_pending=pending)['status'],'STALE')
        self.base.collector.assert_not_called()
        self.base.model.assert_not_called()

    def test_start_injects_server_binding_not_client_binding(self):
        with patch('data.news_investment_service_v1.NewsInvestmentService.start',return_value=(202,{})) as start:
            self.service.start(self.base.binding)
            self.assertEqual(start.call_args.args[0][KEY],self.ref)
        with self.assertRaisesRegex(ValueError,'CLIENT_REFERENCE'):
            self.service.start(self.binding)

    def test_real_pipeline_discovery_port_keeps_jobs_strict(self):
        import test_news_event_pipeline_v1 as event_fixture
        from data.news_event_reference_pipeline_v1 import ReferenceEventNewsPipeline
        events=event_fixture.EventPipelineTests();events.setUp()
        self.addCleanup(events.doCleanups)
        self.service.cache=events.cache
        def context():
            account,target,names=events.service.context()
            account['account_id']='a'
            return account,target,names
        self.service.context=context
        pipeline=ReferenceEventNewsPipeline(self.service,sources_factory=events.factory,
            analyzer=events.analyzer,source_builder=events.pipeline.source_builder,
            clock=events.pipeline.clock,calendar_window=events.pipeline.calendar_window)
        self.assertEqual(pipeline.domain()[0],events.binding)
        pipeline.set_enabled(True)
        result=pipeline.tick()
        self.assertEqual(events.model_calls,1)
        self.assertEqual(result['status'],'SOURCE_OPINION_READY')
        self.assertNotIn(KEY,pipeline.load()['pending']['binding'])
        with self.assertRaisesRegex(ValueError,'REFERENCE_REVIEW_CHANGED'):
            self.service.bound_context(events.binding)
        self.binding=events.binding
        self.assertEqual(self.run_job()['status'],'STALE')


if __name__=='__main__':unittest.main()
