from copy import deepcopy
from datetime import datetime
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

import test_news_investment_service_v1 as service_fixtures
import test_news_scheduled_earnings_v1 as source_fixtures
from data.news_schedule_binding_v1 import context_digest

path = Path(__file__).resolve().parents[1]/'docs/candidates/news_investment_service_scheduled.py'
spec = importlib.util.spec_from_file_location('scheduled_service_candidate', path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class ScheduledServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.base = service_fixtures.ServiceTests(); self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        b = self.base; b.now = datetime.fromisoformat('2026-11-04T05:00:00+00:00')
        root = Path(b.temp.name)
        b.collector.return_value = source_fixtures.ScheduledEarningsTests().fixture(root)
        b.preview['risk_valid_from'] = '2026-11-04T04:59:00Z'
        b.preview['risk_valid_until'] = '2026-11-04T05:05:00Z'
        b.preview['reference_quotes']['A']['reference_valid_until'] = '2026-11-04T05:03:00Z'
        def answer(*args, **kwargs):
            return dict(deepcopy(b.answer), scheduled_context_sha256=context_digest(kwargs['scheduled_context']))
        self.model = Mock(side_effect=answer)
        b.service = module.NewsInvestmentService(cache=root,
            context=lambda:(deepcopy(b.account), deepcopy(b.target), {'A':'MRNA'}),
            preview=b.preview_call, collector=b.collector, source_builder=b.builder,
            model=self.model, clock=lambda:b.now)

    def test_task_passes_calendar_and_preserves_financial_context(self):
        b = self.base; before = deepcopy(b.account)
        result = b.run_job(); self.assertEqual(result['status'], 'COMPLETE')
        calendar = self.model.call_args.kwargs['scheduled_context']
        self.assertEqual(calendar['events'][0]['security_id'], 'A')
        self.assertEqual(result['proposal']['scheduled_context'], calendar)
        self.assertEqual(result['proposal']['review_valid_until'], '2026-11-04T05:03:00+00:00')
        self.assertEqual(b.account, before)
        self.assertFalse(result['proposal']['executable'])

    def test_wrong_model_calendar_binding_rejected(self):
        self.model.side_effect = lambda *a, **k: dict(deepcopy(self.base.answer), scheduled_context_sha256='bad')
        result = self.base.run_job()
        self.assertEqual(result['error'], 'SCHEDULE_MODEL_BINDING_MISMATCH')
        self.assertNotIn('proposal', result)

    def test_raw_calendar_change_during_model_rejected(self):
        original = self.model.side_effect
        def change(*args, **kwargs):
            answer = original(*args, **kwargs)
            for file in (Path(self.base.temp.name)/'raw').glob('*.json'): file.write_bytes(b'changed')
            return answer
        self.model.side_effect = change
        result = self.base.run_job()
        self.assertEqual(result['error'], 'SCHEDULE_CHANGED_DURING_ANALYSIS')
        self.assertNotIn('proposal', result)


if __name__ == '__main__': unittest.main()
