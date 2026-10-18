import ast
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router
from data.strategy_account_identity import PinnedStrategyIdentity

ROOT=Path(__file__).resolve().parents[1]
class MountedAccountTests(unittest.TestCase):
    def test_actual_app_serves_account_component(self):
        from api.server import app
        # No lifespan/startup hooks, research calls, or account initialization.
        response=TestClient(app).get('/static/strategy_account.js')
        self.assertEqual(response.status_code,200,response.text[:200])
        self.assertEqual(response.content,(ROOT/'web/strategy_account.js').read_bytes())
        self.assertIn('javascript',response.headers['content-type'])
    def test_actual_monthly_routes_and_static_read_without_initializing(self):
        from api.server import app, _strategy_monthly_runtime
        before_account = _strategy_monthly_runtime.accounts.path.exists()
        before_target = _strategy_monthly_runtime.targets.path.exists()
        client=TestClient(app)
        response=client.get('/static/strategy_monthly_target.js')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,(ROOT/'web/strategy_monthly_target.js').read_bytes())
        response=client.get('/api/strategy-account/target')
        self.assertEqual(response.status_code,200)
        self.assertIn(response.json()['status'],{'NOT_INITIALIZED','SAVED_TARGET'})
        self.assertEqual(_strategy_monthly_runtime.accounts.path.exists(),before_account)
        self.assertEqual(_strategy_monthly_runtime.targets.path.exists(),before_target)
    def test_server_mount_fixed_identity_pin_read_does_not_create(self):
        tree=ast.parse((ROOT/'api/server.py').read_text(encoding='utf-8'))
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='create_strategy_account_router']
        self.assertEqual(len(calls),1)
        values={x.arg:x.value for x in calls[0].keywords}
        identity=values['resolver'];args=[ast.literal_eval(x) for x in identity.args[1:]]
        descriptor=ROOT/'tmp/tri98_runtime_execution_admission_20261016_v10/descriptor.json'
        raw=descriptor.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(),'aef2c3680d0b2652cf9d141d829a5760193c21581cb948fee0f8e471543e6fce')
        self.assertEqual(json.loads(raw)['source_hashes'][args[0]],args[1])
        resolver=PinnedStrategyIdentity(ROOT,*args)
        evidence=resolver('SNDK');self.assertEqual(evidence['ticker'],'SNDK')
        self.assertIn(args[0],evidence['source_hashes'])
        with TemporaryDirectory() as directory:
            db=Path(directory)/'account.sqlite3';app=FastAPI()
            app.include_router(create_router(database_path=db,account_id=ast.literal_eval(values['account_id']),resolver=resolver))
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/strategy-account').json(),{'status':'NOT_INITIALIZED'})
                self.assertFalse(db.exists())
                first=client.post('/api/strategy-account/initialize',json={'event_id':'explicit-test-init'})
                self.assertEqual(first.status_code,200)
                event={'event_id':'existing-order','kind':'ORDER_OPEN','order_id':'test-only','ticker':'SNDK','side':'BUY','quantity':1,'limit_price':'10','fee_per_share':'0'}
                recorded=client.post('/api/strategy-account/events',json={'expected_revision':first.json()['account']['revision'],'event':event})
                self.assertEqual(recorded.status_code,200,recorded.text)
                self.assertFalse(recorded.json()['account']['cash_confirmation_valid'])

if __name__=='__main__':unittest.main()
