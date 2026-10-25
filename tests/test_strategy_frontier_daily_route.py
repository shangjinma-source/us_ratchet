"""HTTP boundary checks: no legacy or mismatched proposal may expose orders."""
from copy import deepcopy
import unittest
from xml.etree.ElementTree import ParseError

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_frontier_daily_preview_v1 import create_router


class FrontierDailyRouteTests(unittest.TestCase):
    def setUp(self):
        self.body = dict(expected_revision='a'*64, target_id='b'*64,
                         expected_proposal_id='c'*64)
        self.calls = []
        self.result = dict(account_revision='a'*64, target_id='b'*64,
                           proposal_id='c'*64, status='CONDITIONAL_PREVIEW_READY',
                           new_orders=[dict(security_id='test', quantity=1)])
        case = self

        class Service:
            def preview(self, **body):
                case.calls.append(body)
                if isinstance(case.result, Exception):
                    raise case.result
                return deepcopy(case.result)

        app = FastAPI()
        app.include_router(create_router(service=Service()))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, body):
        return self.client.post('/api/strategy-daily-v3/preview', json=body)

    def test_exact_binding_reaches_service(self):
        response = self.post(self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.result)
        self.assertEqual(self.calls, [self.body])
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_ambiguous_or_oversized_http_input_is_rejected(self):
        for response in (
            self.client.post('/api/strategy-daily-v3/preview',
                content='{"target_id":"one","target_id":"two"}'),
            self.client.post('/api/strategy-daily-v3/preview', content=' '*4097),
            self.client.post('/api/strategy-daily-v3/preview?proposal_id=other', json=self.body)):
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.json()['new_orders'], [])
        self.assertEqual(self.calls, [])

    def test_legacy_or_forged_fields_never_call_service(self):
        for body in ({key: value for key, value in self.body.items()
                      if key != 'expected_proposal_id'},
                     dict(self.body, expected_proposal_id=None),
                     dict(self.body, expected_proposal_id='c'*63),
                     dict(self.body, target_quantities={'test': 100})):
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 409)
        self.assertEqual(self.calls, [])

    def test_changed_response_binding_suppresses_all_orders(self):
        original = deepcopy(self.result)
        for field in ('account_revision', 'target_id', 'proposal_id'):
            for replacement in (None, 'd'*64):
                with self.subTest(field=field, replacement=replacement):
                    self.result = dict(original, **{field: replacement})
                    response = self.post(self.body)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()['new_orders'], [])
                    self.assertEqual(response.json()['reference_quotes'], {})

    def test_source_errors_are_non_executable_and_do_not_leak_paths(self):
        for error, reason in ((ParseError('private source'), 'OFFICIAL_ACTION_SOURCE_UNAVAILABLE'),
                              (OSError('private/file'), 'DAILY_PREVIEW_UNAVAILABLE'),
                              (ValueError('STALE_PROPOSAL'), 'STALE_PROPOSAL')):
            with self.subTest(reason=reason):
                self.result = error
                response = self.post(self.body)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()['reason'], reason)
                self.assertEqual(response.json()['new_orders'], [])


if __name__ == '__main__':
    unittest.main()
