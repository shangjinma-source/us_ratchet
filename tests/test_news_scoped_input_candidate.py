"""Scoped-input candidate regression; no production account or external calls."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from threading import get_ident, RLock
from unittest.mock import patch
import unittest
import test_news_investment_service_v1 as fixtures

path = Path(__file__).resolve().parents[1]/'docs/candidates/news_investment_service_scoped_inputs.py'
spec = importlib.util.spec_from_file_location('scoped_service_candidate', path)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)

class ScopedInputTests(fixtures.ServiceTests):
    def setUp(self):
        with patch.object(fixtures, 'NewsInvestmentService', candidate.NewsInvestmentService):
            super().setUp()
        self.depth = 0
        self.scope_threads = []
        self.lock = RLock()
        @contextmanager
        def operation():
            with self.lock:
                self.depth += 1
                self.scope_threads.append(get_ident())
                try:
                    yield
                finally:
                    self.depth -= 1
        self.service.input_operation = operation

    # This inherited test patches Thread in the canonical module; redirect it
    # only during this isolated test to exercise candidate singleflight too.
    def test_start_singleflight_then_cooldown(self):
        import sys
        with patch.dict(sys.modules, {'data.news_investment_service_v1': candidate}):
            super().test_start_singleflight_then_cooldown()

    def test_scope_shared_by_context_and_preview_released_before_model(self):
        calls = []
        prior_context = self.service.context
        def context():
            calls.append(('context', self.depth, get_ident()))
            return prior_context()
        self.service.context = context
        prior_preview = self.preview_call.side_effect
        def preview(**kwargs):
            calls.append(('preview', self.depth, get_ident()))
            return prior_preview(**kwargs)
        self.preview_call.side_effect = preview
        prior_model = self.model.side_effect
        def model(*args, **kwargs):
            self.assertEqual(self.depth, 0)
            return prior_model(*args, **kwargs)
        self.model.side_effect = model
        self.assertEqual(self.run_job()['status'], 'COMPLETE')
        initial = calls[:2]
        self.assertEqual([item[:2] for item in initial], [('context', 1), ('preview', 1)])
        self.assertEqual(initial[0][2], initial[1][2])
        self.assertEqual(len(self.scope_threads), 1)
        self.assertEqual(self.depth, 0)
        self.assertEqual(self.preview_call.call_count, 2)

    def test_scope_unwinds_on_preview_failure_without_model_call(self):
        self.preview_call.side_effect = ValueError('PREVIEW_UNAVAILABLE')
        self.assertEqual(self.run_job()['status'], 'FAILED')
        self.assertEqual(self.depth, 0)
        self.model.assert_not_called()

    def test_real_snapshot_scope_reads_provider_once_for_initial_pair(self):
        from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
        from unittest.mock import Mock
        router = object.__new__(RollingMonthlyRuntimeRouter)
        router.lock = RLock()
        router._active_snapshot = None
        router._loading_snapshot = False
        snapshot = dict(registry_path='registry.json', registry_sha256='a'*64,
                        archive_path='archive.json', archive_sha256='b'*64, revision=1)
        router._snapshot_provider = Mock(return_value=snapshot)
        for name in ('registry_path', 'registry_sha256', 'archive_path', 'archive_sha256'):
            setattr(router, name, snapshot[name])
        self.service.input_operation = router.snapshot_operation
        prior_context = self.service.context
        def context():
            with router.snapshot_operation():
                return prior_context()
        self.service.context = context
        prior_preview = self.preview_call.side_effect
        def preview(**kwargs):
            with router.snapshot_operation():
                return prior_preview(**kwargs)
        self.preview_call.side_effect = preview
        prior_model = self.model.side_effect
        def model(*args, **kwargs):
            # One initial pair + the retained post-input account/target check.
            self.assertEqual(router._snapshot_provider.call_count, 2)
            self.assertIsNone(router._active_snapshot)
            return prior_model(*args, **kwargs)
        self.model.side_effect = model
        self.assertEqual(self.run_job()['status'], 'COMPLETE')
        self.assertIsNone(router._active_snapshot)
        self.assertGreater(router._snapshot_provider.call_count, 2)

if __name__ == '__main__':
    unittest.main()
