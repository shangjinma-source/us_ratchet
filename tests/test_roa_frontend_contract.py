"""Real HTTP JSON responses consumed by the actual JavaScript controller."""
from datetime import datetime, timedelta
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService
from api.roa_strategy import create_router
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_strategy_service import RoaStrategyService


class FrontendContractTests(unittest.TestCase):
    def test_pending_ready_and_expiry_actual_http_json(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[datetime.fromisoformat('2026-11-06T14:00:00+00:00')]
            account=StrategyAccountService(database_path=Path(directory)/'synthetic.sqlite',
                account_id='synthetic',resolver=lambda _:None,clock=lambda:now[0])
            revision=account.initialize({'event_id':'init'})['account']['revision']
            life=RoaExecutionLifecycle(path=Path(directory)/'lifecycle.json',account_id='synthetic',
                strategy_epoch='contract-test',contract_sha256='a'*64)
            signal=dict(signal_id='s',signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,
                weights={'A':'1/10'},execution_not_before_session='2026-11-06',securities=[dict(security_id='A',ticker='A')])
            def calendar(day):return dict(open_at=day+'T14:30:00+00:00',close_at=day+'T21:00:00+00:00')
            def quotes(state,sids,day,phase,clock):
                return dict(opening_session=day,opening_prices={'A':'10'},quote_valid_until=(clock+timedelta(seconds=120)).isoformat(),
                    marks={'A':dict(security_id='A',currency='USD',price_basis='current',price='10',observed_at=clock.isoformat())},
                    limits={'A':dict(security_id='A',price_basis='current',buy='10',sell='10',observed_at=clock.isoformat())})
            service=RoaStrategyService(account_service=account,lifecycle=life,signal_provider=lambda:signal,
                session_provider=calendar,quote_provider=quotes,clock=lambda:now[0],execution_admission=dict(
                    enabled=True,strategy_epoch='contract-test',contract_sha256='a'*64,open_window_seconds=300,close_window_seconds=300))
            app=FastAPI();app.include_router(create_router(coordinator=service))
            with TestClient(app) as client:
                plan=client.get('/api/strategy-roa/snapshot').json()
                saved=client.post('/api/strategy-roa/cash-save-and-preview',json=dict(expected_revision=revision,
                    event=dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))).json()
                self.assertTrue(saved['cash_saved'])
                before=account.store.read();now[0]=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
                ready=client.post('/api/strategy-roa/advice-retry',json={}).json()
                self.assertIsNone(ready.get('cash_saved'))
                self.assertEqual(account.store.read(),before)
            javascript=r'''
const assert=require('node:assert/strict'),fs=require('fs');
const {createController}=require('./web/strategy_roa_controller.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));let response=data.plan,clock=Date.parse('2026-11-06T14:00:00Z');
const controller=createController({request:async()=>response,readAccount:async()=>response.account,
 eventId:()=> 'unused',pendingStore:{read:()=>null,write(){throw Error('unexpected write')},clear(){}},
 expectedEpoch:'contract-test',now:()=>clock});
(async()=>{await controller.load();assert.equal(controller.getState().advice.status,'PENDING_OPEN');
 response=data.ready;clock=Date.parse('2026-11-06T14:31:00Z');await controller.refresh();
 const state=controller.getState();assert.equal(state.error,null);assert.equal(state.advice.executable,true);
 assert.equal(state.advice.rows[0].quantity,9);assert.equal(state.account.revision,state.advice.account_revision);
 clock=Date.parse(state.advice.quote_valid_until);assert.equal(controller.getState().advice,null);
 console.log('HTTP to JS contract PASS');})().catch(e=>{console.error(e);process.exitCode=1});
'''
            result=subprocess.run(['node','-e',javascript],input=json.dumps(dict(plan=plan,ready=ready)),
                text=True,capture_output=True,cwd=Path(__file__).resolve().parents[1],timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
