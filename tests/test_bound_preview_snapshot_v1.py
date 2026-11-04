from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService
from api.strategy_frontier_daily_preview_v1 import create_router
from data.strategy_bound_preview_snapshot_v1 import BoundPreviewSnapshotV1
from data.strategy_observed_frontier_daily_admission_v1 import ObservedFrontierDailyAdmission
from data.saved_frontier_monthly_view_v1 import SavedFrontierProposalStore
from test_saved_monthly_frontier_proposal import native_fixture


class BoundSnapshotTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.month = '2026-10'
        self.account = StrategyAccountService(database_path=root/'account.sqlite3',
            account_id='test-account', resolver=lambda ticker: None, clock=lambda: self.now)
        self.account.initialize({'event_id': 'initialize'})
        target = native_fixture()
        proposal = SavedFrontierProposalStore(root/'proposals.sqlite3').bind(target)
        self.target = dict(target, proposal_id=proposal['proposal_id'], frontier_proposal=proposal,
            risk_monthly_targets=proposal['payload']['proposed_target_quantities'])
        self.binding = dict(expected_revision=self.account.store.read()['revision'],
            target_id=target['target_id'], expected_proposal_id=proposal['proposal_id'])
        self.depth = self.snapshots = 0
        self.hook = lambda: None
        self.source_hook = lambda: None
        self.reply = dict(status='WAIT', reason='WAIT_POLICY_REVIEW_SESSION', new_orders=[],
            reference_quotes={}, account_revision=self.binding['expected_revision'],
            target_id=target['target_id'], proposal_id=proposal['proposal_id'])

        @contextmanager
        def scope():
            if not self.depth:
                self.snapshots += 1
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1

        monthly = SimpleNamespace(snapshot_operation=scope, accounts=self.account.store,
            current=lambda: deepcopy(self.target), _month=lambda: self.month)
        observed = ObservedFrontierDailyAdmission(monthly=monthly,
            service=SimpleNamespace(preview=lambda **kwargs: deepcopy(self.reply)),
            journal=SimpleNamespace(append=lambda *args, **kwargs: None,
                                    record_return=lambda *args: None),
            clock=lambda: self.now, validate_sources=lambda: self.source_hook(), policy_references={})

        def project(state):
            value = self.account.project(state)
            self.hook()
            return value

        self.service = BoundPreviewSnapshotV1(observed=observed, project_account=project)
        app = FastAPI()
        app.include_router(create_router(service=self.service))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self):
        return self.client.post('/api/strategy-daily-v3/preview', json=self.binding)

    def test_real_account_projection_and_shared_scope(self):
        before = self.account.store.read()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        value = response.json()['verified_snapshot']
        self.assertEqual(value['account'], self.account.read()['account'])
        self.assertEqual(value['target']['server_month'], self.month)
        self.assertEqual(value['target']['proposal_id'], self.binding['expected_proposal_id'])
        self.assertEqual(self.account.store.read(), before)
        self.assertEqual(self.snapshots, 1)
        self.assertEqual(self.depth, 0)

    def assert_refused(self):
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['new_orders'], [])
        self.assertNotIn('verified_snapshot', response.json())
        self.assertEqual(self.depth, 0)

    def test_concurrent_cash_write_during_projection(self):
        self.hook = lambda: self.account.append(dict(expected_revision=self.binding['expected_revision'],
            event=dict(kind='CASH_CONFIRM', event_id='external-cash', amount='125',
                       cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assert_refused()
        self.assertEqual(self.account.read()['account']['available_cash'], '125')

    def test_target_changes_during_projection(self):
        self.hook = lambda: self.target.update(proposal_id='f'*64)
        self.assert_refused()

    def test_month_changes_during_projection(self):
        self.hook = lambda: setattr(self, 'month', '2026-11')
        self.assert_refused()

    def test_risk_expiry_during_projection(self):
        self.reply.update(status='HOLD', risk_valid_from=self.now.isoformat(),
            risk_valid_until=(self.now+timedelta(seconds=5)).isoformat())
        self.hook = lambda: setattr(self, 'now', self.now+timedelta(seconds=6))
        self.assert_refused()

    def test_source_change_during_projection(self):
        def changed():
            raise ValueError('SOURCE_CHANGED')
        self.hook = lambda: setattr(self, 'source_hook', changed)
        self.assert_refused()

    def test_quote_expires_after_observer_before_snapshot(self):
        self.reply.update(status='READY', risk_valid_from=self.now.isoformat(),
            risk_valid_until=(self.now+timedelta(seconds=60)).isoformat(),
            new_orders=[dict(security_id='TEST')], reference_quotes={'TEST': dict(
                observed_at=self.now.isoformat(),
                reference_valid_until=(self.now+timedelta(seconds=5)).isoformat())})
        self.hook = lambda: setattr(self, 'now', self.now+timedelta(seconds=6))
        self.assert_refused()

    def test_clock_reverses_during_projection(self):
        self.hook = lambda: setattr(self, 'now', self.now-timedelta(seconds=1))
        self.assert_refused()


if __name__ == '__main__':
    unittest.main()
