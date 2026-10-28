"""No network/model: stage can be selected explicitly, default is released code."""
from contextlib import closing
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


def service_module():
    candidate = os.environ.get('NEWS_EVENT_SERVICE_CANDIDATE')
    if candidate:
        specification = importlib.util.spec_from_file_location('event_service_candidate', candidate)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module
    from data import news_investment_service_v1
    return news_investment_service_v1


MODULE = service_module()


@unittest.skipUnless(hasattr(MODULE.NewsInvestmentService, 'start_event'), 'Event candidate not released; set NEWS_EVENT_SERVICE_CANDIDATE')
class EventFinalizationTests(unittest.TestCase):
    def setUp(self):
        fixture_class = runpy.run_path(str(Path(__file__).with_name('test_news_investment_service_v1.py')))['ServiceTests']
        self.fixture = fixture_class()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        self.service = MODULE.NewsInvestmentService(cache=fixture.service.cache, context=fixture.service.context,
            preview=fixture.preview_call, collector=fixture.collector, source_builder=fixture.builder,
            model=fixture.model, clock=lambda: fixture.now)
        self.service.event_guard = lambda pending: pending['control_generation'] == 1
        fixture.source.update(title='Official', url='https://issuer', tickers=['AAA'])
        answer = deepcopy(fixture.answer)
        answer.update(schema='SOURCE_ONLY_EVENT_OPINION_V1', executable=False, orders_created=False,
                      receipt=dict(finished_at='2026-10-27T14:02:00Z'))
        answer['rows'][0].update(ticker='AAA', holding_fraction='1/1', counterevidence=[], uncertainty=[])
        self.pending = dict(binding=fixture.binding, control_generation=1, execution_window=dict(not_before='2026-10-27T15:00:00Z'), snapshot=dict(events=[]), answer=answer,
                            positions=[dict(security_id='A', ticker='AAA')], source_fingerprint='f',
                            opinion_valid_until='2026-10-27T15:10:00Z')

    def prepare(self):
        with patch('data.news_investment_sources_v1.build_sources', return_value=self.fixture.builder.return_value), patch.object(MODULE.Thread, 'start'):
            code, response = self.service.start_event(self.fixture.binding, self.pending)
        self.assertEqual(code, 202)
        with closing(self.service.connection()) as connection:
            job = json.loads(connection.execute('SELECT document FROM jobs WHERE id=?', (response['job_id'],)).fetchone()[0])
        return job

    def test_two_fresh_previews_without_model_or_recollection(self):
        job = self.prepare()
        self.service.run(job)
        result = self.service.status(job['job_id'])
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['proposal']['rows'][0]['proposed_target_quantity'], 7)
        self.assertEqual(self.fixture.preview_call.call_count, 2)
        self.fixture.model.assert_not_called()
        self.fixture.collector.assert_not_called()
        self.assertFalse(result['proposal']['executable'])

    def test_account_change_after_first_preview_fails(self):
        job = self.prepare()
        def preview(**kwargs):
            self.fixture.account['revision'] = 'changed'
            return deepcopy(self.fixture.preview)
        self.fixture.preview_call.side_effect = preview
        self.service.run(job)
        self.assertEqual(self.service.status(job['job_id'])['status'], 'STALE')
        self.fixture.model.assert_not_called()

    def test_risk_expiry_rejects_even_with_source_opinion(self):
        job = self.prepare()
        self.fixture.preview['risk_valid_until'] = self.fixture.now.isoformat()
        self.service.run(job)
        self.assertEqual(self.service.status(job['job_id'])['status'], 'FAILED')

    def test_wrong_sid_domain_is_not_rebound_to_same_ticker(self):
        self.pending['positions'][0]['security_id'] = 'OTHER'
        with self.assertRaises(ValueError):
            self.prepare()

    def test_failed_source_opinion_cannot_finalize(self):
        self.pending['answer']['status'] = 'FAILED'
        with self.assertRaisesRegex(ValueError, 'SOURCE_ONLY_OPINION_REQUIRED'):
            self.prepare()

    def test_disable_reenable_generation_invalidates_finished_job(self):
        job = self.prepare()
        self.service.run(job)
        self.assertEqual(self.service.status(job['job_id'])['status'], 'COMPLETE')
        self.service.event_guard = lambda pending: pending['control_generation'] == 3
        self.assertEqual(self.service.status(job['job_id'])['status'], 'STALE')

    def test_source_generation_changes_during_requote_rejects(self):
        job = self.prepare()
        calls = []
        def preview(**kwargs):
            calls.append(1)
            if len(calls) == 2:
                self.service.event_guard = lambda pending: False
            return deepcopy(self.fixture.preview)
        self.fixture.preview_call.side_effect = preview
        self.service.run(job)
        with closing(self.service.connection()) as connection:
            saved = json.loads(connection.execute('SELECT document FROM jobs').fetchone()[0])
        self.assertEqual(saved['status'], 'FAILED')
        self.assertNotIn('proposal', saved)

    def test_post_preview_cannot_extend_opinion_execution_window(self):
        from datetime import timedelta
        self.pending['opinion_valid_until'] = '2026-10-27T15:02:00Z'
        job = self.prepare()
        calls = []
        def preview(**kwargs):
            calls.append(1)
            if len(calls) == 2:
                self.fixture.now += timedelta(minutes=1)
            return deepcopy(self.fixture.preview)
        self.fixture.preview_call.side_effect = preview
        self.service.run(job)
        with closing(self.service.connection()) as connection:
            saved = json.loads(connection.execute('SELECT document FROM jobs').fetchone()[0])
        self.assertEqual(saved['status'], 'FAILED')
        self.assertNotIn('proposal', saved)


if __name__ == '__main__':
    unittest.main()
