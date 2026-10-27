"""Published service tests; optional explicit candidate path, no external requests."""
import importlib.util
from pathlib import Path
import runpy,unittest,os
from copy import deepcopy
from unittest.mock import Mock

candidate_path=os.environ.get('NEWS_REVIEW_TEST_CANDIDATE_PATH')
if candidate_path:
    spec=importlib.util.spec_from_file_location('news_timing_candidate',Path(candidate_path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
    from data import news_investment_service_v1 as module
fixture_setup=runpy.run_path('tests/test_news_investment_service_v1.py')['ServiceTests'].setUp

class TimingTests(unittest.TestCase):
    def setUp(self):
        fixture_setup(self)
        self.service=module.NewsInvestmentService(cache=Path(self.temp.name),context=lambda:(deepcopy(self.account),deepcopy(self.target),{'A':'AAA'}),preview=self.preview_call,collector=self.collector,source_builder=self.builder,model=self.model,clock=lambda:self.now)
    def run_job(self):
        job=dict(job_id='j',status='RUNNING',started_at=self.now.isoformat(),binding=self.binding)
        self.service.run(job)
        return self.service.status('j')
    def assert_stages(self,result,names):
        for name in names:
            self.assertIn(name,result['stage_timings'])
            self.assertGreaterEqual(result['stage_timings'][name]['seconds'],0)
        self.assertGreaterEqual(result['worker_elapsed_before_persistence_seconds'],0)
        self.assertIn('excludes queue wait and persistence',result['timing_scope'])
        self.assertNotIn('actual_completion_elapsed_seconds',result)
    def test_success_keeps_both_previews_and_stages(self):
        r=self.run_job();self.assertEqual(r['status'],'COMPLETE')
        self.assert_stages(r,['news_capture','initial_preview','parallel_capture_preview','source_builder','current_analysis_lookup','post_analysis_preview','final_validation','initial_bound_context'])
        self.assertEqual(self.preview_call.call_count,2)
        self.assertEqual(self.model.call_count,1)
        self.assertFalse(r['proposal']['executable'])
        timing=r['proposal']['timeliness']
        self.assertEqual(timing['stage_timings'],r['stage_timings'])
    def test_cache_old_elapsed_distinct_from_current_lookup(self):
        self.answer.update(status='CACHED',receipt={'started_at':'2026-10-26T12:00:00Z','finished_at':'2026-10-26T12:00:40Z','elapsed_seconds':40})
        r=self.run_job();t=r['proposal']['timeliness']
        self.assertTrue(t['cached']);self.assertEqual(t['original_model_elapsed_seconds'],40)
        self.assertEqual(t['original_model_completed_at'],'2026-10-26T12:00:40Z')
        self.assertEqual(t['current_analysis_attempt_completed_at'],self.now.isoformat())
        self.assertLess(t['current_analysis_lookup_seconds'],40)
        self.assertEqual(self.preview_call.call_count,2)
    def test_capture_failure_retains_parallel_measurements(self):
        self.collector.side_effect=ValueError('CAPTURE_FAILED')
        r=self.run_job();self.assertEqual(r['status'],'FAILED')
        self.assert_stages(r,['news_capture','initial_preview','parallel_capture_preview','initial_bound_context'])
        self.assertEqual(r['stage_timings']['news_capture']['status'],'FAILED')
        self.model.assert_not_called()
    def test_model_failure_retains_failed_stage(self):
        self.model.side_effect=ValueError('MODEL_FAILED')
        r=self.run_job();self.assertEqual(r['status'],'FAILED')
        self.assert_stages(r,['current_analysis_lookup','initial_bound_context'])
        self.assertEqual(r['stage_timings']['current_analysis_lookup']['status'],'FAILED')
        self.assertEqual(self.preview_call.call_count,1)
    def test_initial_context_failure_and_stale_telemetry_only(self):
        self.account['revision']='changed'
        r=self.run_job();self.assertEqual(r['status'],'STALE')
        self.assertEqual(r['stage_timings']['initial_bound_context']['status'],'FAILED')
        self.assertNotIn('proposal',r);self.assertNotIn('binding',r)
        self.model.assert_not_called()

    def test_requote_failure_still_recorded(self):
        self.preview_call.side_effect=[deepcopy(self.preview),ValueError('QUOTE_FAILED')]
        r=self.run_job();self.assertEqual(r['status'],'FAILED')
        self.assertEqual(r['stage_timings']['post_analysis_preview']['status'],'FAILED')
        self.assert_stages(r,['initial_bound_context'])

if __name__=='__main__':unittest.main()
