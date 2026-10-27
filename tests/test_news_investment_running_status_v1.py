"""Progress polling must not contend for the financial snapshot lock."""
import importlib.util,os,runpy,unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from threading import Event,Thread
from contextlib import closing

candidate=os.environ.get('NEWS_REVIEW_TEST_CANDIDATE_PATH')
if candidate:
    spec=importlib.util.spec_from_file_location('running_status_candidate',candidate)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
    from data import news_investment_service_v1 as module
fixture_setup=runpy.run_path('tests/test_news_investment_service_v1.py')['ServiceTests'].setUp

class RunningStatusTests(unittest.TestCase):
    def setUp(self):
        fixture_setup(self)
        self.service=module.NewsInvestmentService(cache=Path(self.temp.name),context=lambda:(deepcopy(self.account),deepcopy(self.target),{'A':'AAA'}),preview=self.preview_call,collector=self.collector,source_builder=self.builder,model=self.model,clock=lambda:self.now)
    def save_running(self):
        job=dict(job_id='j',status='RUNNING',started_at=self.now.isoformat(),binding=self.binding,proposal={'private':'must not leak'})
        with closing(self.service.connection()) as connection,connection:self.service.save(connection,job)
    def test_running_returns_without_blocked_context(self):
        self.save_running();entered=Event();release=Event();results=[]
        def blocked_context():
            entered.set();release.wait(3)
            return deepcopy(self.account),deepcopy(self.target),{'A':'AAA'}
        self.service.context=blocked_context
        worker=Thread(target=lambda:results.append(self.service.status('j')),daemon=True)
        worker.start();worker.join(timeout=0.5)
        try:
            self.assertFalse(worker.is_alive(),'progress waited for account context')
            self.assertFalse(entered.is_set())
            self.assertEqual(set(results[0]),{'status','job_id','started_at'})
            self.assertEqual(results[0]['status'],'RUNNING')
        finally:release.set();worker.join(timeout=4)
    def test_running_deadline_without_context(self):
        self.save_running();self.now+=timedelta(seconds=361)
        self.service.context=lambda:(_ for _ in ()).throw(AssertionError('context called'))
        self.assertEqual(self.service.status('j')['error'],'REVIEW_DEADLINE_EXCEEDED')
    def test_unknown_job_unchanged(self):
        self.assertEqual(self.service.status('missing'),{'status':'FAILED','error':'UNKNOWN_JOB'})
    def completed(self):
        self.service.run(dict(job_id='j',status='RUNNING',started_at=self.now.isoformat(),binding=self.binding))
        self.assertEqual(self.service.status('j')['status'],'COMPLETE')
    def test_complete_still_checks_binding(self):
        self.completed();self.account['revision']='different'
        r=self.service.status('j');self.assertEqual(r['status'],'STALE');self.assertNotIn('proposal',r)
    def test_complete_still_checks_expiry(self):
        self.completed();self.now+=timedelta(minutes=4)
        r=self.service.status('j');self.assertEqual(r['status'],'STALE');self.assertNotIn('proposal',r)

if __name__=='__main__':unittest.main()
