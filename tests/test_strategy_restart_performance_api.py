import json
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import create_account, apply_event
from api.strategy_restart_performance import RestartPerformanceService, create_router


class ApiTests(unittest.TestCase):
    def test_pinned_read_only_endpoint_and_conflicts(self):
        state=create_account('fixture')
        state=apply_event(state,dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])[0]
        initial=dict(status='READY',cash_confirmed=True,account_revision=state['revision'],valued_at='2026-11-06T14:30:00Z',market_value='0',strategy_total='1000',holdings=[])
        baseline=dict(initial_equity='1000',cash='1000',effective_at=initial['valued_at'],account_revision=state['revision'],holdings=[],valuation_evidence=initial)
        with tempfile.TemporaryDirectory() as directory:
            paths=[]
            for name,document in [('baseline',baseline),('ledger',state)]:
                path=Path(directory)/name;path.write_text(json.dumps(document),encoding='utf-8');paths.append((path,sha256(path.read_bytes()).hexdigest()))
            current=[state]
            service=RestartPerformanceService(baseline_path=paths[0][0],baseline_sha256=paths[0][1],ledger_path=paths[1][0],ledger_sha256=paths[1][1],read_account=lambda:current[0],valuation=lambda:dict(initial,valued_at='2026-11-06T14:32:00Z',account_revision=current[0]['revision']))
            service.clock=lambda:datetime.fromisoformat('2026-11-06T14:32:00Z')
            app=FastAPI();app.include_router(create_router(service=service));client=TestClient(app)
            url='/api/strategy-account/restart-performance'
            result=client.get(url)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json()['return_fraction'],'0')
            self.assertIsNone(result.json()['maximum_drawdown_fraction'])
            self.assertEqual(client.get(url+'?baseline_path=anything').status_code,409)
            self.assertEqual(client.post(url).status_code,405)
            # A reconciled fill must remain measurable through the real router,
            # including fees; a fresh revision is not automatically an inflow.
            original_valuation = service.valuation
            traded = apply_event(state, dict(event_id='fill', kind='DIRECT_FILL',
                security_id='X', side='BUY', quantity=2, price='100', fees='1',
                executed_at='2026-11-06T14:31:00Z'), expected_revision=state['revision'])[0]
            traded = apply_event(traded, dict(event_id='confirmed', kind='CASH_CONFIRM',
                amount='799', cash_basis='TOTAL_UNINVESTED'), expected_revision=traded['revision'])[0]
            current[0] = traded
            service.valuation = lambda: dict(initial, account_revision=traded['revision'],
                valued_at='2026-11-06T14:32:00Z', market_value='220', strategy_total='1019',
                holdings=[dict(security_id='X', quantity=2, price='110', market_value='220',
                    observed_at='2026-11-06T14:32:00Z')])
            before_read = json.dumps(traded, sort_keys=True)
            filled_result = client.get(url)
            self.assertEqual(filled_result.status_code, 200)
            self.assertEqual(filled_result.json()['return_fraction'], '19/1000')
            self.assertEqual(filled_result.json()['account_revision'], traded['revision'])
            self.assertEqual(json.dumps(current[0], sort_keys=True), before_read)
            current[0] = state
            service.valuation = original_valuation
            service.clock=lambda:datetime.fromisoformat('2026-11-06T14:34:01Z')
            self.assertEqual(client.get(url).json()['reason'],'CURRENT_VALUATION_EXPIRED')
            service.clock=lambda:datetime.fromisoformat('2026-11-06T14:31:59Z')
            self.assertEqual(client.get(url).json()['reason'],'CURRENT_VALUATION_EXPIRED')
            service.clock=lambda:datetime.fromisoformat('2026-11-06T14:32:00Z')
            changed=apply_event(state,dict(event_id='deposit',kind='CASH_CONFIRM',amount='1100',cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])[0]
            current[0]=changed
            self.assertEqual(client.get(url).json()['reason'],'UNCLASSIFIED_CASH_CHANGE')
            current[0]=state
            def race():
                current[0]=changed
                return initial
            service.valuation=race
            self.assertEqual(client.get(url).json()['reason'],'STALE_REVISION')
            paths[0][0].write_text('{}')
            self.assertEqual(client.get(url).json()['reason'],'BASELINE_SOURCE_CHANGED')


if __name__=='__main__': unittest.main()
