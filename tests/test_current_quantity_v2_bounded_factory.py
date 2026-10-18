"""Actual composition and HTTP lifecycle with synthetic quotes and public feed."""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_paper import create_router, PREFIX
from data.current_quantity_v2_bounded_unit_review import BoundedPublicUnitReview
from data.current_quantity_v2_current_cash_factory import create_services
import test_current_quantity_v2_continuation_factory as prior
import test_current_quantity_v2_current_cash_continuation_sources as sources
from test_current_quantity_v2_current_cash_sources import snapshot_fixture, month_config
from test_current_quantity_v2_bounded_unit_review import feed


class BoundedFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources.SourcesTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        sources.SourcesTests.tearDownClass()

    def test_http_current_cash_partial_fill_bounded_continuation_and_retry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots, view = snapshot_fixture(root)
            _, source, clock, quotes = sources.SourcesTests().fixture()
            feeds = []
            reader = BoundedPublicUnitReview(
                fetch=lambda: (feeds.append(1) or {'status': 200, 'body': feed()}),
                clock=lambda: clock[0])
            services = create_services(root=root, snapshot_service=snapshots,
                server_account_id='fixed-pool', database_path=root/'paper.sqlite3',
                fetch=source.fetch, clock=lambda: clock[0], unit_review_reader=reader,
                execution_month_mandate=month_config(root))
            self.assertEqual(feeds, [])
            self.assertFalse(services['store'].path.exists())
            helper = prior.ContinuationFactoryTests(); helper.view = view
            before = helper.closed(services, clock)
            self.assertEqual(before['capabilities']['continuation']['policy'], reader.policy)
            app = FastAPI(); app.include_router(create_router(service=services['paper']))
            with TestClient(app) as client:
                response = client.post(PREFIX+'/continuation/preview', json={
                    'account_id': 'fixed-pool', 'expected_revision': before['revision']})
                self.assertEqual(response.status_code, 200, response.text)
                proposal = response.json()
                self.assertEqual(proposal['unit_review']['policy'], reader.policy)
                self.assertFalse(proposal['unit_review']['coverage_complete'])
                self.assertFalse(proposal['unit_review']['source_authenticated'])
                self.assertNotIn('bounded_evidence', str(proposal))
                self.assertEqual(feeds, [1])
                self.assertEqual(quotes, ['AAA','BBB','AAA','BBB'])
                request = dict(account_id='fixed-pool', proposal_id=proposal['proposal_id'],
                    operation_id='bounded-accept', expected_revision=before['revision'])
                clock[0] += timedelta(seconds=1)
                response = client.post(PREFIX+'/continuation/accept', json=request)
                self.assertEqual(response.status_code, 200, response.text)
                after = response.json()
                for name in ('cash','shares','recorded_fees','target_quantities'):
                    self.assertEqual(after[name], before[name])
                clock[0] += timedelta(days=90)
                with patch.object(reader, 'fetch', side_effect=AssertionError('retry fetch')):
                    self.assertEqual(client.post(PREFIX+'/continuation/accept',json=request).json(), after)
                self.assertEqual(feeds, [1])
                self.assertEqual(quotes, ['AAA','BBB','AAA','BBB'])


if __name__ == '__main__':
    unittest.main()
