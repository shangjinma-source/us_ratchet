"""Isolated real HTTP/SQLite/browser recovery; selection and quotes are fixtures."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import subprocess
import threading
import time
import unittest

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
import uvicorn
from api.strategy_account import create_router as account_router
from api.strategy_frontier_monthly_target_v1 import create_router as target_router
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from test_saved_monthly_frontier_proposal import native_fixture, sign
from test_cash_button_real_ledger_browser import NODE

ROOT = Path(__file__).resolve().parents[1]
BROWSER = r"""
const assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();await page.goto(process.argv[1]);await page.evaluate(()=>ready);
  await page.evaluate(async()=>{try{await daily.saveBalance({amount:'20000'});}catch(error){window.firstFailure=error.message;}});
  assert(await page.evaluate(()=>Boolean(firstFailure)));
  const pending=await page.evaluate(()=>JSON.parse(localStorage.getItem('us-ratchet-pending-monthly-target-v1')));
  assert(pending.event_id);const revision=await page.evaluate(()=>daily.getState().account.revision);
  await page.reload();await page.evaluate(()=>ready);await page.evaluate(()=>daily.refresh());
  const state=await page.evaluate(()=>daily.getState());
  assert.equal(state.account.revision,revision);assert.equal(state.account.available_cash,'20000');
  assert.equal(state.daily.proposal_id,state.target.proposal_id);assert.equal(state.daily.status,'HOLD');
  assert.equal(await page.evaluate(()=>localStorage.getItem('us-ratchet-pending-monthly-target-v1')),null);
  console.log(JSON.stringify({status:'PASS',event_id:pending.event_id}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class RecoveryBrowserTests(unittest.TestCase):
    failure = 'partial'

    def test_reload_recovers_same_target_without_cash_or_selection_replay(self):
        if not NODE.is_file():
            self.skipTest('Browser runtime unavailable')
        with TemporaryDirectory() as folder:
            root = Path(folder)
            now = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
            accounts = StrategyAccountStore(root/'account.sqlite3', clock=lambda: now)
            accounts.initialize('synthetic-account', operation_id='init')
            accounts.append(dict(event_id='initial-cash', kind='CASH_CONFIRM', amount='20000',
                cash_basis='AVAILABLE_AFTER_RESERVATIONS'), expected_revision=accounts.read()['revision'])
            targets = StrategyMonthlyTargetStore(root/'targets.sqlite3')
            selections = []

            class Monthly:
                def snapshot_operation(self): return nullcontext()
                def _month(self): return '2026-11'
                def current(self): return targets.current()
                def generate(self, **request):
                    old = targets.operation(request['event_id'])
                    if old:
                        self_outer.assertEqual(old['payload']['request'], request)
                        return old
                    self_outer.assertEqual(request['expected_revision'], accounts.read()['revision'])
                    selections.append(deepcopy(request))
                    target = native_fixture(month='2026-11')
                    target['payload']['request'] = request
                    target['payload']['decision']['payload']['input_binding']['account_revision'] = request['expected_revision']
                    sign(target)
                    return targets.append(target['payload'])

            self_outer = self
            failure = self.failure

            class Proposals(SavedFrontierProposalStore):
                first = True
                def bind(self, target):
                    if self.first and failure == 'partial':
                        self.first = False
                        raise OSError('isolated interrupted proposal write')
                    return super().bind(target)

            view = SavedFrontierMonthlyView(monthly=Monthly(), proposals=Proposals(root/'proposals.sqlite3'), validate_sources=lambda: None)
            app = FastAPI()
            app.include_router(account_router(database_path=accounts.path, account_id='synthetic-account', resolver=lambda _: None, clock=lambda: now))
            app.include_router(target_router(service=view))
            lost = [False]

            @app.middleware('http')
            async def lose_first_response(request, call_next):
                response = await call_next(request)
                if failure == 'response' and request.url.path.endswith('/target/generate') and not lost[0]:
                    lost[0] = True
                    return PlainTextResponse('isolated lost response', status_code=500)
                return response

            @app.get('/')
            def page():
                return HTMLResponse(''.join('<script src="/'+name+'"></script>' for name in ('account.js','controller.js','recovery.js'))+'''<script>
window.ready=(async()=>{
 window.account=StrategyAccountUI.createController({automaticValuationEnabled:false});await account.load();
 const request=StrategyDailyController.fetchTransport(fetch.bind(window));
 const base=StrategyDailyController.httpDependencies(request,()=>crypto.randomUUID(),account);
 const recovery=StrategyTargetRecoveryV1.create({storage:localStorage,locks:navigator.locks,makeId:()=>crypto.randomUUID()});
 window.daily=StrategyDailyController.createController(StrategyTargetRecoveryV1.dependencies({base,request,recovery}));
 await daily.load();
})();</script>''')

            @app.get('/{name}.js')
            def script(name: str):
                paths = {'account':ROOT/'web/strategy_account.js', 'controller':ROOT/'docs/candidates/strategy_daily_controller_recovery_v2.js', 'recovery':ROOT/'web/strategy_target_recovery_v1.js'}
                return FileResponse(paths[name], media_type='text/javascript')

            @app.post('/api/strategy-daily-v3/preview')
            def preview(body: dict):
                target = view.current()
                self.assertEqual(body['expected_revision'], accounts.read()['revision'])
                self.assertEqual(body['expected_proposal_id'], target['proposal_id'])
                return dict(status='HOLD', account_revision=body['expected_revision'], target_id=target['target_id'],
                    proposal_id=target['proposal_id'], risk_monthly_targets=target['risk_monthly_targets'], new_orders=[], reference_quotes={})

            listener = socket.socket();listener.bind(('127.0.0.1', 0))
            server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
            thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True);thread.start()
            try:
                deadline=time.monotonic()+10
                while not server.started and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(server.started)
                result=subprocess.run([str(NODE),'-e',BROWSER,'http://127.0.0.1:'+str(listener.getsockname()[1])],capture_output=True,text=True,encoding='utf-8',timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)
                receipt=json.loads(result.stdout)
                self.assertEqual(len(selections),1)
                self.assertEqual(len(targets.history()),1)
                self.assertEqual(targets.current()['payload']['request']['event_id'],receipt['event_id'])
                self.assertEqual(sum(e['payload']['kind']=='CASH_CONFIRM' for e in accounts.read()['events']),2)
            finally:
                server.should_exit=True;thread.join(timeout=10);listener.close()


class LostResponseRecoveryBrowserTests(RecoveryBrowserTests):
    failure = 'response'
