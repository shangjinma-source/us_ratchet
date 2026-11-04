"""Account HTTP recovery using temporary ledgers; no production writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_store import StrategyAccountStore

import api.strategy_account as candidate


class AccountWriteReconciliationTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory())
        self.path = Path(temporary)/'account.sqlite3'
        self.store = StrategyAccountStore(self.path)
        app = FastAPI()
        app.include_router(candidate.create_router(database_path=self.path,
            account_id='synthetic', resolver=lambda ticker: dict(ticker=ticker,
                security_id='TEST', source_references=['synthetic.json'],
                source_hashes={'synthetic.json': 'a'*64})))
        self.client = self.enterContext(TestClient(app))
        self.base = '/api/strategy-account'

    def post(self, suffix, body):
        return self.client.post(self.base+suffix, json=body)

    def uncertain_then_retry(self, suffix, body):
        with patch.object(candidate.StrategyAccountService, 'project',
                          side_effect=ValueError('SYNTHETIC_PROJECTION_FAILURE')):
            response = self.post(suffix, body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.json(), dict(status='BLOCKED', reason='RECONCILE_REQUIRED',
            write_may_have_occurred=True, reconcile_before_retry=True))
        committed = self.store.read()
        restored = self.client.get(self.base)
        self.assertEqual(restored.status_code, 200)
        replay = self.post(suffix, body)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()['account'], restored.json()['account'])
        self.assertEqual(self.store.read(), committed)
        return committed

    def test_initialize_response_failure_does_not_repeat_initialization(self):
        self.uncertain_then_retry('/initialize', {'event_id': 'init'})

    def test_cash_response_failure_preserves_single_confirmation(self):
        initial = self.post('/initialize', {'event_id': 'init'}).json()
        state = self.uncertain_then_retry('/events', dict(expected_revision=initial['account']['revision'],
            event=dict(event_id='cash', kind='CASH_CONFIRM', amount='100',
                       cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assertEqual(state['available_cash'], '100')
        self.assertEqual(sum(row['payload']['kind']=='CASH_CONFIRM' for row in state['events']), 1)

    def test_fill_response_failure_preserves_single_fill(self):
        initial = self.post('/initialize', {'event_id': 'init'}).json()
        cash = self.post('/events', dict(expected_revision=initial['account']['revision'],
            event=dict(event_id='cash', kind='CASH_CONFIRM', amount='100',
                       cash_basis='AVAILABLE_AFTER_RESERVATIONS'))).json()
        state = self.uncertain_then_retry('/events', dict(expected_revision=cash['account']['revision'],
            event=dict(event_id='fill', kind='DIRECT_FILL', ticker='TEST', side='BUY',
                quantity=2, price='10', fees='0', executed_at='2026-10-16T14:00:00Z')))
        self.assertEqual(state['shares']['TEST'], 2)
        self.assertEqual(sum(row['payload']['kind']=='DIRECT_FILL' for row in state['events']), 1)

    def test_invalid_input_remains_definite_rejection(self):
        response = self.post('/initialize', {'event_id': 'init', 'extra': True})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('write_may_have_occurred', response.json())
        self.assertIsNone(self.store.read())
