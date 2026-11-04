from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_news_scheduled_earnings_v1 as fixtures
from data.news_scheduled_earnings_v1 import build_scheduled_earnings

candidate = Path(__file__).resolve().parents[1]/'docs/candidates/news_investment_model_scheduled.py'
spec = importlib.util.spec_from_file_location('scheduled_model_candidate', candidate)
model = importlib.util.module_from_spec(spec); spec.loader.exec_module(model)


class ScheduledModelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        snapshot = fixtures.ScheduledEarningsTests().fixture(self.root)
        self.positions = [dict(security_id='mrna', ticker='MRNA', original_qty=0, target_qty=4),
                          dict(security_id='other', ticker='OTHER', original_qty=2, target_qty=2)]
        self.context = build_scheduled_earnings(snapshot, self.root, self.positions)
        self.sources = [dict(id='other-news', security_ids=['other'], tickers=['OTHER'],
            content_kind='FULL_TEXT', text='An actual issuer report.', published_at='2026-11-04T04:00:00Z',
            observed_at='2026-11-04T05:00:00Z')]
        self.answer = dict(rows=[dict(security_id=p['security_id'], ticker=p['ticker'], action='ABSTAIN',
            reason='资料不足', counterevidence=[], uncertainty=['财报安排不是业绩结论'],
            buy_fraction='1/1', holding_fraction='1/1', evidence=[]) for p in self.positions])
        clock = patch.object(model, '_now', return_value='2026-11-04T06:00:00+00:00')
        self.now = clock.start(); self.addCleanup(clock.stop)

    def call(self, context=None):
        return model.analyze_review(self.sources, self.positions, self.root/'analysis',
                                    scheduled_context=self.context if context is None else context)

    def test_real_adapter_prompt_and_cached_binding(self):
        with patch.object(model, '_invoke', return_value=(self.answer, {})) as invoke:
            result = self.call(); self.assertEqual(result['status'], 'SUCCEEDED')
            payload = json.loads(invoke.call_args.args[0].split('\nPUBLIC_INPUT\n')[1])
            self.assertEqual(payload['scheduled_context']['events'][0]['ticker'], 'MRNA')
            self.assertEqual(len(payload['sources']), 1)
            self.assertEqual(self.call()['status'], 'CACHED'); self.assertEqual(invoke.call_count, 1)
            changed = deepcopy(self.context); changed['events'][0]['scheduled_at'] = '2026-11-09T13:00:00+00:00'
            # Coordinator may defer a second live call; the cache identity must differ.
            self.assertNotEqual(self.call(changed)['cache_key'], result['cache_key'])

    def test_calendar_cannot_supply_exit_evidence(self):
        self.answer['rows'][0].update(action='EXIT', buy_fraction='0/1', holding_fraction='0/1',
            evidence=[dict(source_id=self.context['events'][0]['source_id'],
                           quote=self.context['events'][0]['source_quote'])])
        with patch.object(model, '_invoke', return_value=(self.answer, {})):
            self.assertEqual(self.call()['status'], 'FAILED')

    def test_expiry_before_cached_answer_and_during_model(self):
        with patch.object(model, '_invoke', return_value=(self.answer, {})):
            self.assertEqual(self.call()['status'], 'SUCCEEDED')
        self.now.return_value = '2026-11-06T13:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'SCHEDULE_CONTEXT_EXPIRED'): self.call()

    def test_expiry_during_inference_refuses_result(self):
        def invoke(*args):
            self.now.return_value = '2026-11-06T13:00:00+00:00'
            return self.answer, {}
        with patch.object(model, '_invoke', side_effect=invoke):
            self.assertEqual(self.call()['status'], 'FAILED')


if __name__ == '__main__': unittest.main()
