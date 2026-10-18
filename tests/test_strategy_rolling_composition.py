"""Synthetic reviewed fixture pins only; real production pins are never generated."""
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
from core.strategy_account_store import StrategyAccountStore
from data.strategy_dynamic_source_gate import DYNAMIC_SOURCE_PATHS
from api.strategy_rolling_composition import create_rolling_strategy_router, COMPOSITION_PATH, ROLLING_SOURCE_PATHS
import test_strategy_account_monthly_router as fixture_module


class RollingCompositionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.MonthlyRouterTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        source_root=Path(__file__).resolve().parents[1]
        self.pins={}
        for name in ROLLING_SOURCE_PATHS:
            raw=(source_root/name).read_bytes();target=self.root/name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            self.pins[name]=sha256(raw).hexdigest()
        self.arguments=dict(root=self.root,registry_path='registry.json',
            registry_sha256=self.fixture.fixture.put('registry.json',self.fixture.fixture.registry),
            archive_path='archive.json',archive_sha256=self.fixture.fixture.put('archive.json',self.fixture.archive),
            source_pins=self.pins,identity_configuration=self.fixture.configuration,
            bootstrap_configuration=self.fixture.configuration,clock=lambda:self.fixture.now,
            runtime_builder=self.fixture.build)

    def client(self):
        router=create_rolling_strategy_router(**self.arguments)
        parent=APIRouter();parent.include_router(router)
        app=FastAPI();app.include_router(parent)
        result=TestClient(app);self.addCleanup(result.close)
        return result

    def test_nested_include_all_endpoints_gated_and_constructor_copies_pins(self):
        client=self.client()
        self.pins.clear()
        self.assertEqual(client.get('/api/strategy-account').status_code,200)
        self.assertEqual(client.get('/api/strategy-account/target').json()['status'],'NOT_INITIALIZED')
        path=self.root/COMPOSITION_PATH;path.write_bytes(b'changed')
        for method,url,body in [('GET','/api/strategy-account',None),
                ('GET','/api/strategy-account/target',None),
                ('GET','/api/strategy-account/valuation',None),
                ('GET','/api/strategy-account/holding-bars',None),
                ('GET','/api/strategy-account/target/bars',None),
                ('POST','/api/strategy-account/initialize',{}),
                ('POST','/api/strategy-account/events',{}),
                ('POST','/api/strategy-account/target/generate',{}),
                ('POST','/api/strategy-account/target/preview',{})]:
            response=client.request(method,url,json=body)
            self.assertEqual(response.status_code,503,response.text)
            self.assertFalse(response.json()['write_may_have_occurred'])
            self.assertEqual(response.json()['gate_phase'],'BEFORE_OPERATION')
        self.assertIsNone(self.fixture.router.current())

    def test_real_fill_and_target_generate_preview(self):
        client=self.client();f=self.fixture
        target=client.post('/api/strategy-account/target/generate',json=f.request())
        self.assertEqual(target.status_code,200,target.text)
        before=f.router.accounts.read()
        preview=client.post('/api/strategy-account/target/preview',json=dict(
            target_id=target.json()['target_id'],expected_revision=before['revision']))
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['core_calls'],0)
        row=f.fixture.identity['candidates'][0]
        event=dict(event_id='actual-fill',kind='DIRECT_FILL',ticker=row['ticker'],side='BUY',
            quantity=1,price='100',fees='0',executed_at=f.now.isoformat())
        response=client.post('/api/strategy-account/events',json=dict(event=event,expected_revision=before['revision']))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(f.router.accounts.read()['shares'][row['security_id']],1)
        self.assertEqual(f.selection_calls,1)

    def test_post_gate_failure_reports_possible_committed_write(self):
        client=self.client();f=self.fixture
        before=f.router.accounts.read()
        event=dict(event_id='cash-written',kind='CASH_CONFIRM',amount='1900',cash_basis='TOTAL_UNINVESTED')
        original=StrategyAccountStore.append
        def append(store,*args,**kwargs):
            result=original(store,*args,**kwargs)
            (self.root/COMPOSITION_PATH).write_bytes(b'changed after commit')
            return result
        with patch.object(StrategyAccountStore,'append',append):
            response=client.post('/api/strategy-account/events',json=dict(event=event,expected_revision=before['revision']))
        self.assertEqual(response.status_code,503,response.text)
        self.assertTrue(response.json()['write_may_have_occurred'])
        self.assertTrue(response.json()['reconcile_before_retry'])
        self.assertEqual(response.json()['gate_phase'],'AFTER_OPERATION')
        self.assertNotIn('effect',response.json())
        self.assertEqual(f.router.accounts.read()['cash'],'1900')

    def test_read_post_gate_failure_hides_success_without_claiming_account_write(self):
        from api.strategy_account import StrategyAccountService
        client=self.client()
        original=StrategyAccountService.read
        def read(service):
            result=original(service)
            (self.root/COMPOSITION_PATH).write_bytes(b'changed during read')
            return result
        with patch.object(StrategyAccountService,'read',read):
            response=client.get('/api/strategy-account')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['gate_phase'],'AFTER_OPERATION')
        self.assertFalse(response.json()['write_may_have_occurred'])
        self.assertNotIn('cash',response.json())

    def test_missing_self_pin_rejected_without_construction(self):
        del self.pins[COMPOSITION_PATH]
        with self.assertRaisesRegex(ValueError,'ROLLING_COMPOSITION_SCOPE_REQUIRED'):
            self.client()


class RollingReadyHTTPTests(unittest.TestCase):
    def test_real_ready_activation_is_seen_by_existing_http_chart_and_restart(self):
        import json
        import test_review_prepare_real_monthly_release as fixtures
        from scripts.review_prepare_real_monthly_release import run
        from data.strategy_account_release_activation import MonthlyReleaseActivation
        f = fixtures.ReviewPrepareTests(); f.setUp(); self.addCleanup(f.doCleanups)
        ready = run(**f.arguments)
        configuration = json.loads((f.root/'reviewed-package/candidate/runtime.json').read_bytes())
        pins = {}
        source_root = Path(__file__).resolve().parents[1]
        for name in ROLLING_SOURCE_PATHS:
            raw = (source_root/name).read_bytes(); target = f.root/name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        # Initial approved archive already includes this bootstrap; the active
        # candidate adds the reviewed registry binding without replacing it.
        initial = dict(registry_path=f.arguments['registry_path'],
            registry_sha256=f.arguments['registry_sha256'],
            archive_path=ready['files']['archive']['path'],
            archive_sha256=ready['files']['archive']['sha256'])
        arguments = dict(root=f.root, **initial, source_pins=pins,
            bootstrap_configuration=configuration, identity_configuration=configuration, clock=lambda:f.now)
        def client():
            app = FastAPI(); nested = APIRouter()
            nested.include_router(create_rolling_strategy_router(**arguments)); app.include_router(nested)
            result = TestClient(app); self.addCleanup(result.close); return result
        http = client()
        before = f.store.path.read_bytes()
        self.assertEqual(http.get('/api/strategy-account/target').json()['status'], 'NOT_INITIALIZED')
        sid = f.f.identity['candidates'][0]['security_id']
        query = dict(account_revision=f.store.read()['revision'], security_id=sid, interval='day')
        first = http.get('/api/strategy-account/holding-bars', params=query)
        self.assertEqual(first.status_code, 200, first.text)
        activation = MonthlyReleaseActivation(root=f.root, initial_snapshot=initial,
            validate_code=lambda:None, clock=lambda:f.now)
        receipt = 'reviewed-package/ready.json'
        activation.adopt(receipt_path=receipt,
            receipt_sha256=sha256((f.root/receipt).read_bytes()).hexdigest(), expected_release_revision=0)
        # Break the initial archive binding in the private constructor value:
        # active reads must now use their captured active snapshot.
        arguments['archive_sha256'] = '0'*64
        restarted = client()
        for current in (http, restarted):
            response = current.get('/api/strategy-account/holding-bars', params=query)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['bars'], first.json()['bars'])
            self.assertEqual(current.get('/api/strategy-account/target').json()['status'], 'NOT_INITIALIZED')
        self.assertEqual(before, f.store.path.read_bytes())
        self.assertFalse((f.root/'data/strategy_account/monthly_targets.sqlite3').exists())
        (f.root/'data/strategy_account_release_activation.py').write_bytes(b'drift')
        blocked = http.get('/api/strategy-account/holding-bars', params=query)
        self.assertEqual(blocked.status_code, 503)
        self.assertEqual(blocked.json()['gate_phase'], 'BEFORE_OPERATION')


if __name__=='__main__':unittest.main()
