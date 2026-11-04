from copy import deepcopy
from datetime import timedelta
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_current_preview_v1 import create_router
from data.strategy_current_preview_v1 import CurrentPreviewV1
from test_bound_preview_snapshot_v1 import BoundSnapshotTests


class CurrentReadTests(unittest.TestCase):
    def setUp(self):
        self.fixture = BoundSnapshotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = CurrentPreviewV1(bound_preview=self.fixture.service)
        app = FastAPI()
        app.include_router(create_router(service=self.service))
        self.client = self.enterContext(TestClient(app))

    def get(self, query=''):
        return self.client.get('/api/strategy-daily-v3/current'+query)

    def test_current_account_target_and_advice_share_single_operation(self):
        before = self.fixture.account.store.read()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['account'], result['daily']['verified_snapshot']['account'])
        self.assertEqual(result['target'], result['daily']['verified_snapshot']['target'])
        self.assertEqual(result['daily']['account_revision'], before['revision'])
        self.assertEqual(self.fixture.snapshots, 1)
        self.assertEqual(self.fixture.account.store.read(), before)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_missing_or_old_target_returns_configuration_without_generation(self):
        for case in ('missing', 'old'):
            with self.subTest(case=case):
                saved = deepcopy(self.fixture.target)
                if case == 'missing': self.fixture.target = None
                else: self.fixture.month = '2026-11'
                response = self.get()
                self.assertEqual(response.status_code, 200)
                value = response.json()
                self.assertIsNone(value['daily'])
                self.assertEqual(value['target']['configuration_reason'],
                                 'INITIAL' if case == 'missing' else 'MONTHLY_SELECTION')
                self.assertFalse(value['orders_created'])
                self.fixture.target = saved
                self.fixture.month = '2026-10'

    def test_saved_cash_revision_constraint_rejects_later_account(self):
        response = self.get('?expected_revision='+'f'*64)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('account', response.json())
        self.assertNotIn('daily', response.json())

    def test_account_changes_during_combined_read_refused(self):
        fixture = self.fixture
        fixture.hook = lambda: fixture.account.append(dict(
            expected_revision=fixture.binding['expected_revision'],
            event=dict(kind='CASH_CONFIRM', event_id='external', amount='120',
                       cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        response = self.get()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('daily', response.json())

    def test_missing_target_snapshot_rechecks_month_after_projection(self):
        self.fixture.target = None
        self.fixture.hook = lambda: setattr(self.fixture, 'month', '2026-11')
        self.assertEqual(self.get().status_code, 409)

    def test_expired_quotes_cannot_escape_current_route(self):
        fixture = self.fixture
        fixture.reply.update(status='READY', risk_valid_from=fixture.now.isoformat(),
            risk_valid_until=(fixture.now+timedelta(seconds=60)).isoformat(),
            new_orders=[dict(security_id='TEST')], reference_quotes={'TEST': dict(
                observed_at=fixture.now.isoformat(),
                reference_valid_until=(fixture.now+timedelta(seconds=5)).isoformat())})
        fixture.hook = lambda: setattr(fixture, 'now', fixture.now+timedelta(seconds=6))
        response = self.get()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['new_orders'], [])
        self.assertNotIn('daily', response.json())

    def test_no_client_target_override_or_write_route(self):
        for query in ('?target_id=x', '?expected_revision=bad',
                      '?expected_revision='+'a'*64+'&expected_revision='+'b'*64):
            self.assertEqual(self.get(query).status_code, 409)
        self.assertEqual(self.client.post('/api/strategy-daily-v3/current').status_code, 405)

    def test_source_failure_reasons_preserved_and_unknown_details_hidden(self):
        from xml.etree.ElementTree import ParseError
        for error, reason in (
            (ParseError('private source path'), 'OFFICIAL_ACTION_SOURCE_UNAVAILABLE'),
            (ValueError('EVIDENCE_UNAVAILABLE'), 'EVIDENCE_UNAVAILABLE'),
            (ValueError('SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW'), 'WAIT_KNOWN_ACTION_REVIEW'),
            (OSError('private local path'), 'CURRENT_ADVICE_UNAVAILABLE')):
            with self.subTest(reason=reason):
                def fail(**kwargs): raise error
                self.service.read = fail
                response = self.get()
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()['reason'], reason)
                self.assertNotIn('private', response.text)


if __name__ == '__main__':
    unittest.main()
