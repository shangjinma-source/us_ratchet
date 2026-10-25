import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_daily_preview_v4 import create_router
from api.strategy_error_boundary_v1 import StrategyErrorBoundary

class Service:
    def __init__(self, error=None): self.error=error
    def preview(self, **kwargs):
        if self.error: raise self.error
        return dict(status='HOLD', new_orders=[], reference_quotes={})

class BoundaryTests(unittest.TestCase):
    def client(self, error=None, enabled=True):
        app=FastAPI()
        if enabled: app.add_middleware(StrategyErrorBoundary)
        app.include_router(create_router(service=Service(error)))
        @app.post('/api/strategy-account/events')
        def write(): raise RuntimeError('private account content')
        @app.get('/api/strategy-account')
        def read(): raise RuntimeError('private account content')
        @app.get('/unrelated')
        def other(): raise RuntimeError('outside scope')
        return TestClient(app, raise_server_exceptions=False)
    def preview(self, client):
        return client.post('/api/strategy-daily-v3/preview',json={'expected_revision':'a'*64,'target_id':'b'*64})
    def test_reproduces_original_plain_text(self):
        result=self.preview(self.client(RuntimeError('private'),False))
        self.assertEqual(result.status_code,500)
        self.assertEqual(result.text,'Internal Server Error')
    def test_unexpected_preview_is_safe_json(self):
        with self.assertLogs('api.strategy_error_boundary_v1',level='ERROR') as logs:
            result=self.preview(self.client(RuntimeError('private account content')))
        self.assertEqual(result.status_code,500)
        self.assertEqual(result.json()['reason'],'DAILY_RESPONSE_UNAVAILABLE')
        self.assertEqual(result.json()['new_orders'],[])
        self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertNotIn('private',result.text+' '.join(logs.output))
    def test_uncertain_write_requires_reconciliation(self):
        result=self.client().post('/api/strategy-account/events',json={'secret':'not logged'})
        self.assertTrue(result.json()['write_may_have_occurred'])
        self.assertTrue(result.json()['reconcile_before_retry'])
        self.assertEqual(result.json()['reason'],'RECONCILE_REQUIRED')
    def test_normal_and_known_failure_unchanged(self):
        self.assertEqual(self.preview(self.client()).json()['status'],'HOLD')
        result=self.preview(self.client(ValueError('SOURCE_CHANGED')))
        self.assertEqual(result.status_code,409)
        self.assertEqual(result.json()['reason'],'SOURCE_CHANGED')
    def test_scope_and_read(self):
        client=self.client()
        self.assertEqual(client.get('/unrelated').text,'Internal Server Error')
        result=client.get('/api/strategy-account').json()
        self.assertNotIn('write_may_have_occurred',result)
        self.assertEqual(result['reason'],'DAILY_RESPONSE_UNAVAILABLE')

if __name__=='__main__': unittest.main()
