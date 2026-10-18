"""New current-unit target through real raw decoder, SQLite and HTTP routes."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_paper import create_router, PREFIX
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from test_current_quantity_v2_current_cash_ledger import frozen_fixture
import test_current_quantity_v2_current_cash_plan as cash_fixture


def fixture(folder, original_args):
    proposal, args = frozen_fixture(original_args)
    clock = [datetime.fromisoformat(args['now']) + timedelta(seconds=1)]
    store = QuantityV2PaperStore(Path(folder) / 'paper.sqlite3')
    paper = QuantityV2PaperService(store=store, clock=lambda: clock[0],
        initial_resolver=lambda *unused: dict(proposal=proposal, account_state=args['account_state']))
    account = paper.accept(account_id=proposal['account_id'], proposal_id=proposal['proposal_id'], operation_id='initial')
    order = next(o for o in account['orders'] if o['security_id'] == 'A')
    clock[0] += timedelta(seconds=1)
    account = paper.event(account_id=account['account_id'], event=dict(type='FILL', event_id='fill',
        order_id=order['order_id'], expected_revision=account['revision'], quantity=1,
        price='9', fees='1/5', executed_at=clock[0].isoformat()))
    for order in account['orders']:
        clock[0] += timedelta(seconds=1)
        account = paper.event(account_id=account['account_id'], event=dict(type='CANCEL',
            event_id='cancel-' + order['security_id'], order_id=order['order_id'],
            expected_revision=account['revision'], cancelled_at=clock[0].isoformat()))
    package = deepcopy(args['execution_package'])
    files, pins = package['files'], package['source_hashes']
    def put(name, value):
        files[name] = json.dumps(value, sort_keys=True).encode()
        pins[name] = sha256(files[name]).hexdigest()
        return name
    captured = clock[0] + timedelta(seconds=60)
    evidence = put('continuation/evidence.json', {'synthetic': True, 'scope': 'explicit reviewed unit interval'})
    receipts, units = {}, {}
    securities = deepcopy(proposal['securities'])
    for row in proposal['rows']:
        sid = row['security_id']
        raw = json.loads(files['current/' + sid + '.raw'])
        parsed = raw['chart']['result'][0]
        parsed['meta']['regularMarketTime'] = int(captured.timestamp()) - 1
        parsed['timestamp'] = [int(captured.replace(second=0).timestamp()) - 60]
        raw_path = put('continuation/' + sid + '.raw', raw)
        receipt_path = put('continuation/' + sid + '.receipt', dict(security_id=sid,
            ticker=securities[sid]['ticker'], raw_path=raw_path, raw_sha256=pins[raw_path],
            captured_at=captured.isoformat()))
        receipts[sid] = receipt_path
        units[sid] = dict(security_id=sid, ticker=securities[sid]['ticker'],
            security_class=securities[sid]['security_class'], status='NO_UNPROCESSED_ACTIONS',
            price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
            initial_price_basis='PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE',
            initial_execution_target_id=proposal['execution_target_id'],
            initial_reference_source_hashes=deepcopy(row['source_hashes']),
            reference_source_hashes={raw_path:pins[raw_path], receipt_path:pins[receipt_path]},
            covered_from=row['captured_at'], covered_through=captured.isoformat(),
            reviewed_at=captured.isoformat(), source_references=[evidence])
    package['documents'] = dict(capital_decision=put('continuation/decision.json', args['capital_decision']),
        identities=put('continuation/identities.json', dict(securities=securities, source_references=[evidence])),
        unit_continuity=put('continuation/units.json', units), quote_receipts=receipts)
    clock[0] = captured + timedelta(seconds=1)
    bridge = QuantityV2ContinuationSourceBridge(store=store, resolver=lambda *unused: deepcopy(package), clock=lambda: clock[0])
    paper.continuation_previewer = bridge.preview
    paper.continuation_resolver = bridge.continuation_resolver
    return paper, bridge, package, clock, account


class CurrentCashContinuationHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cash_fixture.CurrentCashTests.setUpClass()
        cls.args = deepcopy(cash_fixture.CurrentCashTests.args)
    @classmethod
    def tearDownClass(cls):
        cash_fixture.CurrentCashTests.tearDownClass()

    def test_partial_fill_close_preview_accept_replay_and_retry(self):
        with TemporaryDirectory() as folder:
            paper, bridge, package, clock, account = fixture(folder, self.args)
            before = paper.store.read(account['account_id'])
            app = FastAPI(); app.include_router(create_router(service=paper))
            with TestClient(app) as client:
                body = dict(account_id=account['account_id'], expected_revision=account['revision'])
                response = client.post(PREFIX + '/continuation/preview', json=body)
                self.assertEqual(response.status_code, 200, response.text)
                p = response.json()
                self.assertEqual(p['target_quantities'], {'A':6, 'B':4})
                self.assertEqual(p['historical_target_quantities'], {'A':1, 'B':1})
                self.assertEqual(p['execution_target_id'], account['execution_target_id'])
                self.assertEqual(p['actual_cash'], '504/5')
                self.assertEqual({o['security_id']:o['quantity'] for o in p['orders']}, {'A':5, 'B':4})
                self.assertEqual(p['reserved_buy_cash'], '81')
                request = dict(body, proposal_id=p['proposal_id'], operation_id='continue')
                clock[0] += timedelta(seconds=1)
                accepted = client.post(PREFIX + '/continuation/accept', json=request)
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(accepted.json()['shares'], {'A':1})
                self.assertEqual(accepted.json()['execution_target_id'], account['execution_target_id'])
                self.assertEqual(paper.store.read(account['account_id'])['genesis'], before['genesis'])
                bridge.resolver = lambda *unused: (_ for _ in ()).throw(AssertionError('retry reads source'))
                paper.clock = lambda: (_ for _ in ()).throw(AssertionError('retry reads clock'))
                self.assertEqual(client.post(PREFIX + '/continuation/accept', json=request).json(), accepted.json())

    def test_raw_drift_expiry_or_revision_reject_without_account_write(self):
        for mode in ('raw', 'expiry', 'revision'):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                paper, bridge, package, clock, account = fixture(folder, self.args)
                app = FastAPI(); app.include_router(create_router(service=paper))
                with TestClient(app) as client:
                    body = dict(account_id=account['account_id'], expected_revision=account['revision'])
                    response = client.post(PREFIX + '/continuation/preview', json=body)
                    self.assertEqual(response.status_code, 200, response.text)
                    request = dict(body, proposal_id=response.json()['proposal_id'], operation_id='rejected')
                    before = paper.store.read(account['account_id'])
                    if mode == 'raw':
                        package['files']['continuation/A.raw'] += b' '
                    elif mode == 'expiry':
                        clock[0] += timedelta(seconds=121)
                    else:
                        request['expected_revision'] = 'stale'
                    result = client.post(PREFIX + '/continuation/accept', json=request)
                    self.assertNotEqual(result.status_code, 200, result.text)
                    self.assertEqual(result.json()['orders'], [])
                    self.assertEqual(paper.store.read(account['account_id']), before)


if __name__ == '__main__':
    unittest.main()
