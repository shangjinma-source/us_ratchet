"""Real browser/account API/SQLite, synthetic preview; never uses live accounts."""
import json
import socket
import subprocess
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from api.strategy_account import create_router
from core.strategy_account_store import StrategyAccountStore

ROOT = Path(__file__).resolve().parents[1]
NODE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')

BROWSER = r"""
const assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try {
  const page=await browser.newPage();await page.goto(process.argv[1]);
  await page.evaluate(async()=>{
   window.account=StrategyAccountUI.createController({automaticValuationEnabled:false,onInvalidate:()=>window.daily?.accountInvalidated?.()});
   await account.load();
   window.daily=StrategyDailyMount.mount(document.getElementById('daily'),{
    ...StrategyDailyController.httpDependencies(StrategyDailyController.fetchTransport(fetch.bind(window)),()=>crypto.randomUUID(),account)
   });await daily.ready;await daily.refresh();
  });
  const input=page.locator('input[name=amount]');const button=page.getByRole('button',{name:'更新现金并查看建议',exact:true});
  assert.equal((await page.evaluate(()=>daily.getState())).daily.new_orders[0].limit_price,'10');
  await input.fill('120');await button.click();await page.evaluate(()=>daily.whenIdle());
  let state=await page.evaluate(()=>daily.getState());
  assert.equal(state.error,process.argv[2]);
  assert.equal(state.daily,null);
  assert.equal(state.historicalOrders.S[0].limit_price,'10');
  assert((await page.locator('#daily').innerText()).includes('已失效'));
  assert(!(await page.locator('#daily').innerText()).includes('Unexpected token'));assert.equal(state.cashSaved,true);
  assert.equal(state.account.available_cash,'120');const savedRevision=state.account.revision;
  await button.click();await page.evaluate(()=>daily.whenIdle());
  state=await page.evaluate(()=>daily.getState());assert.equal(state.error,null);
  assert.equal(state.daily.status,'READY');assert.equal(state.account.revision,savedRevision);
  assert.equal(state.daily.account_revision,savedRevision);
  assert.equal(state.daily.new_orders[0].limit_price,'9');
  assert.equal(state.historicalOrders.S,undefined);
  assert(!(await page.locator('#daily').innerText()).includes('上一条建议'));
  assert((await page.locator('#daily').innerText()).includes('买入 1 股'));
  // A later ordinary balance confirmation replaces cash, never adds it.
  await button.click();await page.evaluate(()=>daily.whenIdle());
  state=await page.evaluate(()=>daily.getState());assert.equal(state.account.available_cash,'120');
  assert.equal(state.daily.account_revision,state.account.revision);assert.equal(state.target.target_id,'a'.repeat(64));
  console.log(JSON.stringify({status:'REAL_LEDGER_BROWSER_RETRY_PASS',retry_revision_unchanged:true,final_cash:state.account.available_cash}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class CashButtonLedgerBrowserTests(unittest.TestCase):
    failure_kind = "structured"
    def test_saved_cash_preview_failure_retry_and_repeat_confirmation(self):
        if not NODE.is_file():
            self.skipTest('Local browser runtime unavailable')
        with TemporaryDirectory() as folder:
            now = datetime.now(timezone.utc)
            database = Path(folder) / 'isolated.sqlite3'
            store = StrategyAccountStore(database, clock=lambda: now)
            store.initialize('isolated-browser-test', operation_id='init')
            store.append(dict(event_id='initial-cash', kind='CASH_CONFIRM', amount='100',
                              cash_basis='AVAILABLE_AFTER_RESERVATIONS'),
                         expected_revision=store.read()['revision'])
            initial = store.read()
            app = FastAPI()
            app.include_router(create_router(database_path=database,
                account_id='isolated-browser-test', resolver=lambda ticker: None,
                clock=lambda: now))
            target_id = 'a' * 64
            month = now.strftime('%Y-%m')
            preview_revisions = []

            @app.get('/')
            def page():
                return HTMLResponse('<div id="daily"></div>' + ''.join(
                    '<script src="/web/' + name + '"></script>' for name in
                    ('strategy_account.js', 'strategy_daily_controller.js', 'strategy_daily_mount.js')))

            @app.get('/web/{name}')
            def script(name: str):
                assert name in ('strategy_account.js', 'strategy_daily_controller.js', 'strategy_daily_mount.js')
                return FileResponse(ROOT / 'web' / name, media_type='text/javascript')

            @app.get('/api/strategy-account/target')
            def target():
                return dict(target_id=target_id, target_month=month, server_month=month,
                            targets=[dict(security_id='S', ticker='TEST', quantity=1)])

            @app.post('/api/strategy-daily-v3/preview')
            async def preview(request: Request):
                body = await request.json()
                current = store.read()
                self.assertEqual(body, dict(expected_revision=current['revision'], target_id=target_id))
                preview_revisions.append(current['revision'])
                if len(preview_revisions) == 2:
                    if self.failure_kind == 'non_json':
                        return PlainTextResponse('Internal Server Error', status_code=500)
                    return JSONResponse(status_code=409, content=dict(
                        status='WAIT', reason='OFFICIAL_ACTION_SOURCE_UNAVAILABLE'))
                expiry = '2099-01-01T00:00:00Z'
                price = '10' if len(preview_revisions) == 1 else '9'
                order = dict(security_id='S', ticker='TEST', side='BUY', quantity=1,
                             limit_price=price, estimated_cash_change='-' + price, reference_valid_until=expiry)
                return dict(status='READY', account_revision=current['revision'], target_id=target_id,
                    new_orders=[order], reference_quotes={'S': dict(buy=price, sell=price, reference_valid_until=expiry)},
                    effective_target_quantities={'S': 1}, daily_gate=dict(status='DAILY_TARGET_READY',
                    rows=[dict(security_id='S', action='BUY', held=0, effective_target=1)]))

            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
            thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(server.started)
                result = subprocess.run([str(NODE), '-e', BROWSER,
                    'http://127.0.0.1:' + str(listener.getsockname()[1]),
                    'DAILY_RESPONSE_UNAVAILABLE' if self.failure_kind == 'non_json' else 'OFFICIAL_ACTION_SOURCE_UNAVAILABLE'],
                    capture_output=True, text=True, encoding='utf-8', timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'REAL_LEDGER_BROWSER_RETRY_PASS')
                final = store.read()
                self.assertEqual(final['available_cash'], '120')
                self.assertEqual(final['shares'], initial['shares'])
                self.assertEqual(final['orders'], initial['orders'])
                cash_events = [event for event in final['events'] if event['payload']['kind'] == 'CASH_CONFIRM']
                self.assertEqual(len(cash_events), 3)  # setup + first save + later confirmation
                self.assertEqual(len(preview_revisions), 4)
                self.assertNotEqual(preview_revisions[0], preview_revisions[1])
                self.assertEqual(preview_revisions[1], preview_revisions[2])
                self.assertNotEqual(preview_revisions[2], preview_revisions[3])
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                listener.close()
                self.assertFalse(thread.is_alive())


class NonJsonCashButtonLedgerBrowserTests(CashButtonLedgerBrowserTests):
    failure_kind = 'non_json'


if __name__ == '__main__':
    unittest.main()
