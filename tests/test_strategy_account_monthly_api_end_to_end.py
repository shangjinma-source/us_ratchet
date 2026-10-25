"""Synthetic HTTP integration with the real tiny V2 selector; not performance evidence."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_account import create_router as account_router
from api.strategy_monthly_target import create_router as target_router
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_target_service import StrategyAccountTargetService, MINIMUM_RUNTIME_PATHS
from data.strategy_monthly_target_service import StrategyMonthlyTargetService, LIFECYCLE_PATHS
from test_strategy_account_target_decision import fixture, ROOT


class AccountMonthlyHTTPTests(unittest.TestCase):
    def test_cash_real_selection_pending_partial_fill_and_reconfirmation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            arguments, original_limits = fixture(folder)
            now = datetime.fromisoformat(arguments['now'])
            database = root / 'http-account.sqlite3'
            store = StrategyAccountStore(database, clock=lambda: now)
            target_store = StrategyMonthlyTargetStore(root / 'http-target.sqlite3')
            runtime = root / 'runtime'
            pins = {}
            for name in MINIMUM_RUNTIME_PATHS | LIFECYCLE_PATHS:
                raw = (ROOT / name).read_bytes()
                destination = runtime / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                pins[name] = sha256(raw).hexdigest()

            provider_revisions = []

            def selection_evidence(state):
                # Rebind synthetic source evidence to the actual HTTP-written ledger.
                provider_revisions.append(state['revision'])
                evidence = {key: deepcopy(arguments[key]) for key in
                            ('source_package', 'manifest_path', 'marks_path', 'unit_review_path')}
                package = evidence['source_package']
                review_path = evidence['unit_review_path']
                review = json.loads(package['files'][review_path])
                review['account_revision'] = state['revision']
                package['files'][review_path] = canonical(review)
                package['source_hashes'][review_path] = sha256(package['files'][review_path]).hexdigest()
                return evidence

            selection = StrategyAccountTargetService(
                store=store, evidence_provider=selection_evidence,
                runtime_root=runtime, runtime_pins=pins,
                maximum_mark_age_seconds=120, execution_fee_bps='0', clock=lambda: now)

            def execution_evidence(state, target, at):
                marks = json.loads(arguments['source_package']['files'][arguments['marks_path']])
                limits = deepcopy(original_limits)
                for value in limits.values():
                    value.update(ticker='SNDK', buy_reason='synthetic test buy',
                                 sell_reason='synthetic test sell',
                                 reference_valid_until=(now + timedelta(seconds=120)).isoformat())
                return dict(marks=marks, limits=limits)

            monthly = StrategyMonthlyTargetService(
                selection_service=selection, target_store=target_store,
                execution_provider=execution_evidence, clock=lambda: now)

            def resolver(ticker):
                self.assertEqual(ticker, 'SNDK')
                return dict(ticker=ticker, security_id='B', source_references=['synthetic-identity'],
                            source_hashes={'synthetic-identity': 'a' * 64})

            app = FastAPI()
            app.include_router(account_router(database_path=database, account_id='strategy',
                                               resolver=resolver, clock=lambda: now))
            app.include_router(target_router(service=monthly))
            base = '/api/strategy-account'
            with TestClient(app) as client:
                self.assertEqual(client.get(base).json()['status'], 'NOT_INITIALIZED')
                self.assertEqual(client.get(base + '/target').json()['configuration_reason'], 'INITIAL')
                self.assertFalse(database.exists())
                self.assertFalse(target_store.path.exists())
                account = client.post(base + '/initialize', json={'event_id': 'http-init'}).json()['account']

                def event(payload):
                    nonlocal account
                    response = client.post(base + '/events', json={
                        'expected_revision': account['revision'], 'event': payload})
                    self.assertEqual(response.status_code, 200, response.text)
                    account = response.json()['account']
                    return response.json()

                event(dict(event_id='http-open', kind='ORDER_OPEN', order_id='sndk-14',
                           ticker='SNDK', side='BUY', quantity=14,
                           limit_price='1322.21', fee_per_share='0'))
                self.assertFalse(account['cash_confirmation_valid'])
                # Hypothetical $500 spendable balance, NOT the user's actual cash.
                event(dict(event_id='http-cash', kind='CASH_CONFIRM', amount='500',
                           cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                self.assertEqual(account['reserved_cash'], '925547/50')
                cash_revision = account['revision']
                before_selection = database.read_bytes()
                generated = client.post(base + '/target/generate', json=dict(
                    event_id='http-target', reason='INITIAL', expected_revision=cash_revision,
                    previous_target_id=None))
                self.assertEqual(generated.status_code, 200, generated.text)
                target = generated.json()
                self.assertEqual(target['targets'], [dict(security_id='B', ticker='SNDK', quantity=14)])
                self.assertEqual(selection.current[0]['core_calls'], 1)
                self.assertEqual(provider_revisions, [cash_revision])
                self.assertEqual(database.read_bytes(), before_selection)

                def preview():
                    return client.post(base + '/target/preview', json=dict(
                        expected_revision=account['revision'], target_id=target['target_id']))

                result = preview()
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['difference']['new_orders'], [])
                self.assertEqual(result.json()['difference']['spendable_cash'], '500')
                self.assertEqual(database.read_bytes(), before_selection)

                event(dict(event_id='http-partial', kind='FILL', order_id='sndk-14', quantity=5,
                           price='1322.21', fees='0', executed_at=(now - timedelta(seconds=60)).isoformat()))
                self.assertEqual(account['holdings'], [dict(security_id='B', ticker='SNDK', quantity=5)])
                self.assertEqual(account['orders'][0]['remaining_quantity'], 9)
                self.assertFalse(account['cash_confirmation_valid'])
                self.assertEqual(preview().json()['reason'], 'CASH_RECONFIRMATION_REQUIRED')
                event(dict(event_id='http-reconfirm', kind='CASH_CONFIRM', amount='500',
                           cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                after_fill = database.read_bytes()
                result = preview()
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['difference']['new_orders'], [])
                self.assertEqual(provider_revisions, [cash_revision], 'Refresh must not reselect')
                self.assertEqual(database.read_bytes(), after_fill)
                self.assertEqual(client.get(base + '/target').json()['target_id'], target['target_id'])

                # A recorded cancellation releases the remaining nine shares for a new
                # suggestion only after a manual cash confirmation; not a broker action.
                event(dict(event_id='http-cancel', kind='CANCEL', order_id='sndk-14'))
                event(dict(event_id='http-cash-after-cancel', kind='CASH_CONFIRM', amount='12399.89',
                           cash_basis='TOTAL_UNINVESTED'))
                result = preview()
                self.assertEqual(result.status_code, 200, result.text)
                orders = result.json()['difference']['new_orders']
                self.assertEqual([(row['side'], row['quantity']) for row in orders], [('BUY', 9)])
                self.assertEqual(orders[0]['ticker'], 'SNDK')
                self.assertEqual(orders[0]['limit_price'], '132221/100')
                self.assertEqual(provider_revisions, [cash_revision])
                self.assertEqual(client.get(base).json()['account']['orders'], [])


if __name__ == '__main__':
    unittest.main()
