"""Real HTTP routers/SQLite/difference; synthetic frozen target, no production IO."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router as account_router
from api.strategy_frontier_daily_preview_v1 import create_router as advice_router
from core.strategy_account_store import StrategyAccountStore
from docs.candidates.target_account_bridge_20261106 import preview_target_weights


class HTTPBridgeTests(unittest.TestCase):
    def test_pending_buy_reservation_and_formal_binding_gate(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'isolated.sqlite3'
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            store = StrategyAccountStore(path, clock=lambda: now)
            target, proposal = 'c'*64, 'd'*64
            marks = {s:dict(security_id=s,currency='USD',price_basis='current',observed_at=now.isoformat(),price='100') for s in ['OLD','NEW']}
            limits = {s:dict(security_id=s,price_basis='current',observed_at=now.isoformat(),buy='100',sell='100') for s in marks}

            class Harness:
                bound = True
                def preview(self, expected_revision, target_id, expected_proposal_id):
                    if (target_id, expected_proposal_id) != (target, proposal):
                        raise ValueError('STALE_TARGET')
                    result = preview_target_weights(account=store.read(),expected_revision=expected_revision,
                        weights={'NEW':'1'},marks=marks,limits=limits,signal_at='2026-11-05T21:00:00Z',
                        valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T14:32:00Z',
                        now=now.isoformat(),contract_hash='b'*64)
                    # This is an explicitly synthetic wiring harness, not an
                    # authenticated production target/provider implementation.
                    if self.bound:
                        result.update(target_id=target_id,proposal_id=expected_proposal_id)
                    return result

            harness = Harness()
            app = FastAPI()
            app.include_router(account_router(database_path=path,account_id='isolated',clock=lambda:now,
                resolver=lambda ticker:dict(ticker=ticker,security_id=ticker,
                    source_references=['synthetic-identity'],source_hashes={'synthetic-identity':'a'*64})))
            app.include_router(advice_router(service=harness))
            with TestClient(app) as client:
                account = client.post('/api/strategy-account/initialize',json={'event_id':'init'}).json()['account']
                def event(payload):
                    nonlocal account
                    response = client.post('/api/strategy-account/events',json=dict(expected_revision=account['revision'],event=payload))
                    self.assertEqual(response.status_code,200,response.text)
                    account = response.json()['account']
                def preview(**extra):
                    body = dict(expected_revision=account['revision'],target_id=target,expected_proposal_id=proposal)
                    body.update(extra)
                    return client.post('/api/strategy-daily-v3/preview',json=body)
                event(dict(event_id='old-fill',kind='DIRECT_FILL',ticker='OLD',side='BUY',quantity=3,price='100',fees='0',executed_at='2026-11-05T15:00:00Z'))
                event(dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
                prior = account['revision']
                event(dict(event_id='pending',kind='ORDER_OPEN',order_id='p',ticker='NEW',side='BUY',quantity=4,limit_price='100',fee_per_share='0'))
                self.assertEqual(preview().status_code,409)  # reservations require reconfirmation
                event(dict(event_id='confirm',kind='CASH_CONFIRM',amount='600',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                before = store.read()
                response = preview()
                self.assertEqual(response.status_code,200,response.text)
                result = response.json()
                self.assertEqual(result['target_quantities'],{'NEW':13})
                orders = {(o['security_id'],o['side']):o['quantity'] for o in result['difference']['new_orders']}
                self.assertEqual(orders,{('OLD','SELL'):3,('NEW','BUY'):6})
                self.assertEqual(store.read(),before)
                self.assertFalse(result['executable'])
                self.assertEqual(preview(expected_revision=prior).json()['reason'],'STALE_REVISION')
                self.assertEqual(preview(expected_proposal_id='e'*64).json()['reason'],'STALE_TARGET')
                self.assertEqual(preview(weights={'NEW':'1'}).json()['reason'],'FRONTIER_BODY_FIELDS')
                harness.bound = False
                rejected = preview()
                self.assertEqual(rejected.status_code,409)
                self.assertEqual(rejected.json()['reason'],'FRONTIER_RESPONSE_BINDING_MISMATCH')
                self.assertEqual(rejected.json()['new_orders'],[])


if __name__ == '__main__':
    unittest.main()
