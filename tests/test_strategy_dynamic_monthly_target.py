"""Dynamic monthly HTTP composition uses saved target history, never reselects."""
import json
from datetime import datetime
from hashlib import sha256
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from api.strategy_dynamic_monthly_target import create_dynamic_monthly_target_router, create_dynamic_account_router
import test_strategy_account_monthly_router as fixtures


class DynamicMonthlyChartTests(unittest.TestCase):
    def test_real_fill_http_resolves_identity_and_exact_retry_once(self):
        fixture = fixtures.MonthlyRouterTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.router = fixture.make_router(identity_configuration=fixture.configuration)
        fixture.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        app = FastAPI()
        app.include_router(create_dynamic_account_router(service=fixture.router))
        candidate = fixture.fixture.identity['candidates'][0]
        request = dict(expected_revision=fixture.router.accounts.read()['revision'], event=dict(
            event_id='record-buy',kind='DIRECT_FILL',ticker=candidate['ticker'],side='BUY',
            quantity=1,price='100',fees='0',executed_at=fixture.now.isoformat()))
        with TestClient(app) as client:
            response = client.post('/api/strategy-account/events', json=request)
            self.assertEqual(response.status_code, 200, response.text)
            account = response.json()['account']
            self.assertEqual(account['holdings'][0]['security_id'], candidate['security_id'])
            self.assertEqual(account['holdings'][0]['quantity'], 1)
            self.assertFalse(account['cash_confirmation_valid'])
            again = client.post('/api/strategy-account/events', json=request)
            self.assertEqual(again.status_code, 200, again.text)
            self.assertEqual(again.json()['account'], account)
            invalid = dict(request,expected_revision=account['revision'],event=dict(request['event'],event_id='unknown',ticker='UNKNOWN'))
            rejected = client.post('/api/strategy-account/events', json=invalid)
            self.assertEqual(rejected.status_code, 422, rejected.text)
            self.assertEqual(fixture.router.accounts.read()['revision'], account['revision'])
            self.assertEqual(fixture.selection_calls, 0)

    def test_real_dispatch_archive_chart_and_no_reselection(self):
        fixture = fixtures.MonthlyRouterTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original_build = fixture.build
        def builder(**kwargs):
            runtime = original_build(**kwargs)
            original_select = runtime.selection.select
            def select():
                result = original_select()
                decision, evidence, state = runtime.selection.current
                manifest = json.loads((fixture.root/kwargs['configuration']['training_manifest']).read_bytes())
                binding = decision['payload']['input_binding']
                binding['source_hashes'].update(manifest['source_hashes'])
                binding['training_cutoff_date'] = manifest['decision_date']
                decision['payload']['input_id'] = sha256(canonical(binding)).hexdigest()
                decision['decision_id'] = sha256(canonical(decision['payload'])).hexdigest()
                return result
            runtime.selection.select = select
            return runtime
        fixture.router._builder = builder
        app = FastAPI()
        app.include_router(create_dynamic_monthly_target_router(service=fixture.router))
        before = fixture.router.accounts.path.read_bytes()
        with TestClient(app) as client:
            base = '/api/strategy-account/target'
            response = client.post(base+'/generate', json=fixture.request())
            self.assertEqual(response.status_code, 200, response.text)
            target = response.json()
            sid = target['targets'][0]['security_id']
            for interval in ('day','week','month'):
                response = client.get(base+'/bars', params=dict(target_id=target['target_id'], security_id=sid, interval=interval))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['bars'])
                self.assertTrue(response.json()['historical_only'])
                self.assertEqual(response.json()['daily_as_of'], target['historical_training_cutoff'])
            stale = client.get(base+'/bars', params=dict(target_id='0'*64,security_id=sid,interval='day'))
            self.assertEqual(stale.status_code, 409, stale.text)
            wrong = client.get(base+'/bars', params=dict(target_id=target['target_id'],security_id='not-selected',interval='day'))
            self.assertEqual(wrong.status_code, 422, wrong.text)
            self.assertEqual(wrong.json()['reason'], 'CHART_NOT_SELECTED')
            fixture.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
            old = client.get(base+'/bars', params=dict(target_id=target['target_id'],security_id=sid,interval='day'))
            self.assertEqual(old.status_code, 200, old.text)
            binding = fixture.router.current()['payload']['decision']['payload']['input_binding']
            manifest = json.loads((fixture.root/binding['documents']['training_manifest']).read_bytes())
            source = next(row['training_source'] for row in manifest['candidates'] if row['security_id']==sid)
            source_path = fixture.root/source
            original = source_path.read_bytes()
            source_path.write_bytes(original+b' ')
            try:
                bad = client.get(base+'/bars', params=dict(target_id=target['target_id'],security_id=sid,interval='day'))
                self.assertEqual(bad.status_code, 422, bad.text)
                self.assertEqual(bad.json()['reason'], 'CHART_SOURCE_CHANGED')
            finally:
                source_path.write_bytes(original)
            self.assertEqual(fixture.selection_calls, 1)
            self.assertEqual(fixture.router.accounts.path.read_bytes(), before)
            (fixture.root/'runtime.json').write_bytes(b'changed')
            refused = client.get(base+'/bars', params=dict(target_id=target['target_id'],security_id=sid,interval='day'))
            self.assertEqual(refused.status_code, 422)
            self.assertEqual(refused.json()['reason'], 'REGISTRY_SOURCE_CHANGED')


if __name__ == '__main__':
    unittest.main()
