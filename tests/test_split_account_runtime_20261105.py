"""HTTP timing and exact snapshot service binding, temporary journal only."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from types import SimpleNamespace
import unittest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.strategy_split_bundle_v1 import prepare_split_bundle
from api.strategy_frontier_daily_preview_v1 import create_router as daily_router
from docs.candidates import split_account_runtime_20261105 as runtime
import test_strategy_split_bundle_v1 as fixtures


class Tests(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.SplitBundleTests(); self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        prepare_split_bundle(**self.base.arguments)
        self.path = self.base.directory / 'account.sqlite3'
        state = SplitStrategyAccountStore(self.path).read()
        action = next(r['payload'] for r in state['events'] if r['payload']['kind'] == 'SPLIT_CONFIRMED')
        self.now = datetime.fromisoformat('2026-10-30T13:30:30+00:00')
        calendar = dict(schema='FIXED_EXCHANGE_SESSIONS_V1', exchange='NASDAQ', sessions=[
            dict(date=d, open=d+'T13:30:00Z', close=d+'T20:00:00Z') for d in ['2026-10-29', '2026-10-30']])
        proof = dict(schema='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2', action_id=action['action_id'],
            recorded_action_sha256=sha256(canonical(action)).hexdigest(), distribution_at=action['effective_at'],
            quote_unit_effective_at='2026-10-30T13:30:00Z', broker_tradable_at='2026-10-30T13:30:00Z',
            tradable_evidence_received_at='2026-10-30T13:30:20Z',
            tradable_evidence_semantics='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE',
            clock_source_references={k:['s'] for k in ['distribution_at','quote_unit_effective_at',
                'broker_tradable_at','tradable_evidence_received_at']})
        self.bundles = {action['action_id']: dict(review=proof, source_hex={'s':b'synthetic'.hex()},
            source_hashes={'s':sha256(b'synthetic').hexdigest()}, calendar=calendar,
            calendar_sha256=sha256(canonical(calendar)).hexdigest())}
        self.mark = dict(security_id='A', ticker='A', currency='USD', price='13', unit_id='new',
                         observed_at=self.now.isoformat())

    def router(self, provider=None):
        return runtime.create_router(database_path=self.path, account_id='synthetic-account',
            resolver=lambda ticker: None, clock=lambda:self.now, timing_bundles=self.bundles,
            valuation_provider=provider or (lambda state:{'A':deepcopy(self.mark)}))

    def test_http_rejects_fresh_pre_quote_mark_and_accepts_current_units(self):
        app=FastAPI();app.include_router(self.router())
        with TestClient(app) as client:
            self.mark['observed_at']='2026-10-30T13:29:59Z'
            result=client.get('/api/strategy-account/valuation')
            self.assertEqual(result.status_code,422)
            self.assertEqual(result.json()['reason'],'VALUATION_PRE_QUOTE_UNIT')
            self.mark['observed_at']=self.now.isoformat()
            result=client.get('/api/strategy-account/valuation')
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json()['market_value'],'1456')

    def test_http_valuation_rejects_account_change_during_source_read(self):
        store=SplitStrategyAccountStore(self.path,clock=lambda:self.now)
        def provider(state):
            store.append(dict(event_id='concurrent-cash',kind='CASH_CONFIRM',amount='5000',
                              cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])
            return {'A':deepcopy(self.mark)}
        app=FastAPI();app.include_router(self.router(provider))
        with TestClient(app) as client:
            result=client.get('/api/strategy-account/valuation')
            self.assertEqual(result.status_code,409)
            self.assertEqual(result.json()['reason'],'STALE_REVISION')

    def test_snapshot_binds_exact_split_service_and_same_database(self):
        observed=SimpleNamespace(monthly=SimpleNamespace(accounts=SplitStrategyAccountStore(self.path)))
        router=APIRouter();router.include_router(self.router());router.include_router(daily_router(service=observed))
        prepared=runtime.attach_bound_snapshot(prepared=dict(router=router,observed_daily=observed),validate_sources=lambda:None)
        snapshot=prepared['bound_snapshot_daily']
        self.assertIs(snapshot.observed,observed)
        self.assertIs(type(snapshot.project_account.__self__),runtime.StrategyAccountService)
        self.assertEqual(snapshot.project_account.__self__.store.path.resolve(),self.path.resolve())
        observed.monthly.accounts=SplitStrategyAccountStore(self.path.parent/'wrong.sqlite3')
        with self.assertRaisesRegex(ValueError,'V30_ACCOUNT_DATABASE_MISMATCH'):
            runtime.attach_bound_snapshot(prepared=dict(router=router,observed_daily=observed),validate_sources=lambda:None)


if __name__=='__main__': unittest.main()
