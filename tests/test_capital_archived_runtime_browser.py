"""Browser click -> real isolated ledger/selector/archive/V23 HTTP -> visible advice.

Vendor data and the V22 mounting base remain fixtures. One HTTP 500 is injected
after capital publication to verify user-visible retry without duplicate credit.
"""
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from api.strategy_monthly_target import create_router
import test_capital_supplement_archived_runtime as fixture
from test_cash_button_real_ledger_browser import NODE

ROOT = Path(__file__).resolve().parents[1]
BROWSER = r"""
const assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(process.argv[1]);
  const mountPage=()=>page.evaluate(async()=>{
   window.account=StrategyAccountUI.createController({automaticValuationEnabled:false,onInvalidate:()=>window.daily?.accountInvalidated?.()});
   await account.load();const request=StrategyDailyController.fetchTransport(fetch.bind(window));
   window.daily=StrategyDailyMount.mount(document.getElementById('daily'),{
    ...StrategyDailyController.httpDependencies(request,()=>crypto.randomUUID(),account),
    now:()=>Date.parse('2026-11-03T15:00:00Z'),onChange:state=>window.capital?.adviceRefreshed(state)
   });await daily.ready;
   const capitalContainer=document.createElement('div');capitalContainer.id='capital';daily.elements.cashPanel.appendChild(capitalContainer);
   const readSnapshot=async()=>{const [a,t]=await Promise.all([request('/api/strategy-account'),request('/api/strategy-account/target')]);return {account:a.account,target:t};};
   window.capital=StrategyCapitalMount.mount(capitalContainer,{
    request,readSnapshot,eventId:()=> 'joint-new-capital',
    pendingStore:StrategyCapitalController.browserPendingStore(localStorage,'isolated-capital-browser'),
    onPublished:async()=>{await account.load();await daily.reloadCash();return daily.refresh();},
    onBalanceChanged:async()=>{await account.load();await daily.reloadCash();},onBusy:value=>daily.setCapitalBusy(value)
   });await capital.ready;
  });await mountPage();
  const original=await page.evaluate(()=>daily.getState().target.target_id);
  await page.locator('#capital input').fill('3000');
  await page.evaluate(()=>{capital.elements.submit.click();capital.elements.submit.click();});
  await page.evaluate(()=>capital.whenIdle());
  if(process.argv[3]==='arrival-response-loss'){
   assert.equal((await page.evaluate(()=>capital.getState())).status,'PENDING_RECOVERY');
   await page.reload();await mountPage();await page.evaluate(()=>capital.whenIdle());
   const recovered=await page.evaluate(()=>daily.getState());
   assert.equal(recovered.account.available_cash,'3100');
   assert.equal(recovered.target.target_id,original,'reload must not silently reconfigure');
   assert.equal(await page.locator('#capital input').isVisible(),false);
   await page.getByRole('button',{name:'核对上次配置',exact:true}).click();
   await page.evaluate(()=>capital.whenIdle());
  }
  let state=await page.evaluate(()=>daily.getState());
  assert.equal(state.account.available_cash,'3100');assert.notEqual(state.target.target_id,original);
  assert.equal(state.daily,null);assert.equal(state.error,'DAILY_RESPONSE_UNAVAILABLE');
  assert.match(await page.locator('#capital').innerText(),/资金和配置已保存.*今日建议未更新/);
  assert.doesNotMatch(await page.locator('body').innerText(),/Unexpected token/);
  assert.equal((await page.evaluate(()=>capital.getState())).pending,null);
  await page.screenshot({path:process.argv[2]+'/failure.png',fullPage:true});
  await page.evaluate(()=>{
   daily.elements.form.requestSubmit();
   daily.elements.form.requestSubmit();
  });
  await page.evaluate(()=>daily.whenIdle());state=await page.evaluate(()=>daily.getState());
  assert.equal(state.error,null);assert.equal(state.account.available_cash,'3100');assert.equal(state.daily.status,'READY');
  assert.equal(state.daily.target_id,state.target.target_id);assert.equal(state.daily.account_revision,state.account.revision);
  assert.deepEqual(state.daily.new_orders.map(o=>[o.security_id,o.side,o.quantity]),[['A','SELL',1],['B','BUY',9]]);
  const visible=await page.locator('#daily').innerText();assert.match(visible,/卖出 1 股/);assert.match(visible,/买入.*9 股/);
  assert.doesNotMatch(visible,/上一条建议/);assert.deepEqual(errors,[]);
  assert.doesNotMatch(await page.locator('#capital').innerText(),/今日建议未更新/);
  await page.screenshot({path:process.argv[2]+'/ready.png',fullPage:true});
  console.log(JSON.stringify({status:'CAPITAL_BROWSER_ARCHIVED_RUNTIME_PASS',cash:state.account.available_cash,
   target_id:state.target.target_id,account_revision:state.account.revision,page_errors:errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


class CapitalBrowserTests(fixture.ArchivedCapitalAdviceTests):
    arrival_response_loss = False
    def verify_advice_http(self, c, risk_reader):
        # Browser already consumed this fixed-clock signal through the real HTTP
        # route. Reusing its timestamp as a fresh event correctly fails admission.
        self.assertEqual(self.browser_receipt['status'], 'CAPITAL_BROWSER_ARCHIVED_RUNTIME_PASS')
        self.assertEqual(self.browser_receipt['target_id'], c.target['target_id'])

    def advice_application(self, c, risk_reader):
        if not hasattr(c, 'browser_app'):
            c.browser_app = super().advice_application(c, risk_reader)
        return c.browser_app

    def perform_contribution(self, c, client, body):
        if not NODE.is_file():
            self.fail('Browser runtime required for this acceptance test')
        app = self.advice_application(c, c.risk_reader)
        app.include_router(create_router(service=c.capital_monthly))
        counts = dict(arrive=0, configure=0, preview=0)
        proxy = FastAPI()
        proxy.mount('/', app)
        @proxy.middleware('http')
        async def failure_once(request, call_next):
            for key, path in [('arrive','/api/strategy-capital-v2/arrive'),
                              ('configure','/api/strategy-capital-v2/configure'),
                              ('preview','/api/strategy-daily-v3/preview')]:
                if request.url.path == path:
                    counts[key] += 1
                    if key == 'preview' and counts[key] == 1:
                        return PlainTextResponse('Internal Server Error', status_code=500)
                    if key == 'arrive' and counts[key] == 1 and self.arrival_response_loss:
                        response = await call_next(request)
                        self.assertEqual(response.status_code, 200)
                        return PlainTextResponse('Arrival response lost', status_code=502)
            return await call_next(request)
        scripts = ('strategy_account.js','strategy_daily_controller.js','strategy_daily_mount.js',
                   'strategy_capital_controller.js','strategy_capital_mount.js')
        @app.get('/')
        def page():
            return HTMLResponse('<meta charset="utf-8"><style>body{font:16px sans-serif;padding:24px}td,th{padding:12px}input,button{padding:12px;margin:8px}</style>'
                '<div id="daily"></div>' + ''.join('<script src="/web/'+name+'"></script>' for name in scripts))
        @app.get('/web/{name}')
        def script(name: str):
            if name not in scripts:
                return PlainTextResponse('not found', status_code=404)
            return FileResponse(ROOT/'web'/name, media_type='text/javascript')
        output = ROOT/'tmp'/('capital_browser_20261024_'+uuid4().hex[:8])
        output.mkdir()
        before = c.store.read()
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(proxy, log_level='error'))
        thread = threading.Thread(target=lambda:server.run(sockets=[listener]), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertTrue(server.started)
            result = subprocess.run([str(NODE), '-e', BROWSER,
                'http://127.0.0.1:'+str(listener.getsockname()[1]), str(output),
                'arrival-response-loss' if self.arrival_response_loss else 'normal'],
                capture_output=True, text=True, encoding='utf-8', timeout=90)
            (output/'browser.log').write_text(result.stdout+result.stderr, encoding='utf-8')
            (output/'http-counts.json').write_text(json.dumps(counts), encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.browser_receipt = receipt
            self.assertEqual(counts, dict(arrive=1, configure=1, preview=2))
            after = c.store.read()
            self.assertEqual(after['available_cash'], '3100')
            self.assertEqual(after['shares'], before['shares'])
            self.assertEqual(after['orders'], before['orders'])
            receipt.update(http_counts=counts, isolated=True, production_account_writes=False)
            receipt['arrival_response_loss_reload'] = self.arrival_response_loss
            (output/'result.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print('BROWSER_ACCEPTANCE='+str(output))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            self.assertFalse(thread.is_alive())


class CapitalArrivalRecoveryBrowserTests(CapitalBrowserTests):
    arrival_response_loss = True
