"""Use the real router scope and original news binding checks, without network."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
import unittest

from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from data.news_investment_service_v1 import NewsInvestmentService
from data.news_event_pipeline_v1 import EventNewsPipeline

path = Path(os.environ.get('NEWS_COMPOSITION_CANDIDATE', 'data/news_investment_composition_v1.py'))
spec = importlib.util.spec_from_file_location('candidate_news_composition', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DomainSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.router = object.__new__(RollingMonthlyRuntimeRouter)
        self.router.lock = RLock()
        self.router._active_snapshot = None
        self.router._loading_snapshot = False
        self.snapshot = dict(registry_path='registry.json', registry_sha256='a'*64,
                             archive_path='archive.json', archive_sha256='b'*64, revision=1)
        for key, value in self.snapshot.items():
            if key != 'revision':
                setattr(self.router, key, value)
        self.provider_calls = self.context_calls = 0
        self.revisions = []
        self.change_account = self.fail_context = self.fail_provider = False
        def provider():
            self.provider_calls += 1
            if self.fail_provider:
                raise ValueError('SOURCE_CHANGED')
            return deepcopy(self.snapshot)
        self.router._snapshot_provider = provider
        def context():
            with self.router.snapshot_operation() as current:
                self.context_calls += 1
                self.revisions.append(current['revision'])
                if self.fail_context:
                    raise ValueError('CONTEXT_FAILED')
                revision = 'r2' if self.change_account and self.context_calls % 2 == 0 else 'r1'
                return dict(revision=revision,shares={'S':1}), dict(target_id='t',proposal_id='p',payload={'target_quantities':{'S':2}}), {'S':'TEST'}
        service = NewsInvestmentService(cache=Path(self.directory.name), context=context, preview=lambda **kwargs:None)
        self.pipeline = EventNewsPipeline(service)

    def test_two_binding_reads_one_snapshot_and_no_cross_call_cache(self):
        original = self.pipeline.domain()
        self.assertEqual((self.provider_calls,self.context_calls),(2,2))
        module.bind_event_domain_snapshot(self.pipeline,self.router)
        self.assertEqual(self.pipeline.domain(),original)
        self.assertEqual((self.provider_calls,self.context_calls),(3,4))
        self.snapshot['revision'] = 2
        self.assertEqual(self.pipeline.domain(),original)
        self.assertEqual((self.provider_calls,self.context_calls),(4,6))
        self.assertEqual(self.revisions[-2:],[2,2])

    def test_account_change_between_binding_reads_still_rejected(self):
        module.bind_event_domain_snapshot(self.pipeline,self.router)
        self.change_account = True
        with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):
            self.pipeline.domain()
        self.assertEqual((self.provider_calls,self.context_calls),(1,2))
        self.assertIsNone(self.router._active_snapshot)

    def test_failures_release_scope_and_next_call_revalidates(self):
        module.bind_event_domain_snapshot(self.pipeline,self.router)
        for attribute,error in [('fail_provider','SOURCE_CHANGED'),('fail_context','CONTEXT_FAILED')]:
            setattr(self,attribute,True)
            with self.assertRaisesRegex(ValueError,error):
                self.pipeline.domain()
            self.assertIsNone(self.router._active_snapshot)
            self.assertFalse(self.router._loading_snapshot)
            setattr(self,attribute,False)
        self.assertEqual(self.pipeline.domain()[0]['expected_revision'],'r1')
        self.assertEqual(self.provider_calls,3)


if __name__ == '__main__':
    unittest.main()
