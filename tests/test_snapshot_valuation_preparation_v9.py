from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
import test_unified_publication_guard_v7 as fixture
from data.strategy_unified_server_preparation_v9 import attach_snapshot_valuation

class SnapshotHTTPTests(unittest.TestCase):
    def setup_case(self, folder):
        c, monthly, prepared = fixture.UnifiedPublicationGuardTests().setup_case(folder)
        routes = APIRouter()
        @routes.get('/api/strategy-account/valuation')
        def old(): raise AssertionError('old valuation path')
        @routes.get('/existing-v8-route')
        def retained(): return {'preserved': True}
        prepared['router'] = routes
        gate_calls = []
        result = attach_snapshot_valuation(prepared=prepared, root=monthly.root,
            validate_valuation_sources=lambda: gate_calls.append(True))
        app = FastAPI(); app.include_router(result['router'])
        return c, monthly, result, TestClient(app), gate_calls

    def test_actual_saved_provider_http_and_route_preservation(self):
        with TemporaryDirectory() as folder:
            c,m,p,client,gates = self.setup_case(folder)
            before=m.accounts.path.read_bytes(),m.targets.path.read_bytes()
            runtime,_=m._for_target(m.current());provider=runtime.execution_provider.__self__
            with patch.object(provider,'training',side_effect=AssertionError('no full training')):
                response=client.get('/api/strategy-account/valuation')
            self.assertEqual(response.status_code,200);self.assertEqual(response.json()['status'],'READY')
            self.assertTrue(response.json()['holdings']);self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(client.get('/existing-v8-route').json(),{'preserved':True})
            self.assertEqual(before,(m.accounts.path.read_bytes(),m.targets.path.read_bytes()))
            self.assertEqual(sum(r.path=='/api/strategy-account/valuation' for r in p['router'].routes),1)
            self.assertGreater(len(gates),3)

    def test_query_and_wait_without_capture(self):
        with TemporaryDirectory() as folder:
            c,m,p,client,_=self.setup_case(folder)
            with patch.object(p['snapshot_valuation'],'valuation',side_effect=AssertionError('query must reject')):
                response=client.get('/api/strategy-account/valuation?anything=1')
                self.assertEqual(response.status_code,409);self.assertEqual(response.json()['reason'],'QUERY_FIELDS')
                self.assertEqual(response.headers['cache-control'],'no-store')
            c.clock[0]=c.clock[0].replace(hour=22)
            response=client.get('/api/strategy-account/valuation')
            self.assertEqual(response.json()['status'],'WAIT_REGULAR_SESSION')

    def test_post_service_source_gate_prevents_response(self):
        with TemporaryDirectory() as folder:
            c,m,p,client,_=self.setup_case(folder)
            original=p['snapshot_valuation'].valuation
            def changed():
                result=original()
                source=m.root/'data/strategy_account_evidence_provider.py'
                source.write_bytes(source.read_bytes()+b'\n')
                return result
            with patch.object(p['snapshot_valuation'],'valuation',side_effect=changed):
                response=client.get('/api/strategy-account/valuation')
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['status'],'BLOCKED')

class ConfigurationTests(unittest.TestCase):
    def test_fixed_sources_checked_before_base_factory(self):
        from pathlib import Path
        from hashlib import sha256
        from core.strategy_account_ledger import canonical
        from data.strategy_unified_server_preparation_v9 import build_unified_server_preparation_v9, VALUATION_SOURCES
        with TemporaryDirectory() as folder:
            root=Path(folder); repository=Path(__file__).resolve().parents[1]
            pins={}
            for name in VALUATION_SOURCES:
                raw=(repository/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
            base=b'{}';(root/'base.json').write_bytes(base)
            config=canonical(dict(schema='SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9',base_v8=dict(path='base.json',sha256=sha256(base).hexdigest()),source_pins=pins))
            (root/'v9.json').write_bytes(config)
            (root/'data/strategy_saved_target_valuation_v1.py').write_bytes(b'changed')
            with patch('data.strategy_unified_server_preparation_v9.build_unified_server_preparation_v8',side_effect=AssertionError('must gate before base')):
                with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
                    build_unified_server_preparation_v9(root=root,configuration_path='v9.json',configuration_sha256=sha256(config).hexdigest())

if __name__=='__main__': unittest.main()
