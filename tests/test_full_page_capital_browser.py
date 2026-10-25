"""Production single-cash page recovers an old capital intent in isolation."""
import json
import socket
import subprocess
import threading
import time
from datetime import timedelta
from uuid import uuid4
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from api.strategy_monthly_target import create_router
import test_capital_archived_runtime_browser as fixture
import test_account_fill_advice_handoff_http as v24

BROWSER = r"""
const assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.clock.install({time:new Date(process.argv[3])});
  await page.goto(process.argv[1]);
  await page.waitForFunction(()=>window.RealStrategyCapital&&!realStrategyInitializing&&
    !realStrategyHeaderRefreshing&&!RealStrategyDaily.getState().busy);
  const before=await page.evaluate(()=>RealStrategyDaily.getState());
  assert.equal(await page.locator('#strategyCapitalAction input').isVisible(),false);
  // Reproduce a persisted intent from the old UI; new UI cannot create one.
  await page.evaluate(body=>{
   const state=RealStrategyDaily.getState();
   localStorage.setItem('us_ratchet.capital-intent.v1.'+state.account.account_id,JSON.stringify({
    ...body,expected_revision:state.account.revision,previous_target_id:state.target.target_id,operation:'ARRIVAL_V2'}));
  },JSON.parse(process.argv[4]));
  await page.reload();
  await page.waitForFunction(()=>window.RealStrategyCapital&&!realStrategyInitializing&&
    !realStrategyHeaderRefreshing&&!RealStrategyDaily.getState().busy);
  await page.evaluate(()=>RealStrategyCapital.ready);
  assert.equal((await page.evaluate(()=>RealStrategyDaily.getState())).account.available_cash,'100');
  assert.equal(await page.getByRole('button',{name:'更新现金并查看建议',exact:true}).isDisabled(),true);
  await page.evaluate(()=>{RealStrategyCapital.elements.recover.click();RealStrategyCapital.elements.recover.click();});
  await page.evaluate(()=>RealStrategyCapital.whenIdle());
  const after=await page.evaluate(()=>RealStrategyDaily.getState());
  assert.equal(after.account.available_cash,'3100');
  assert.deepEqual(after.account.holdings,before.account.holdings);
  assert.notEqual(after.target.target_id,before.target.target_id);
  if(!after.daily){
   require('node:fs').writeFileSync(process.argv[2]+'/failed-state.json',JSON.stringify({daily:after,capital:await page.evaluate(()=>RealStrategyCapital.getState()),text:await page.locator('#strategyCapitalAction').innerText()},null,2));
   await page.screenshot({path:process.argv[2]+'/failed.png',fullPage:true});
  }
  assert.equal(after.daily?.status,'READY');assert.equal(after.error,null);
  assert.equal(after.daily.target_id,after.target.target_id);
  assert.equal(after.daily.account_revision,after.account.revision);
  assert.deepEqual(after.daily.new_orders.map(row=>[row.security_id,row.side,row.quantity]),[['A','SELL',1],['B','BUY',9]]);
  assert.match(await page.locator('#strategyCapitalAction').innerText(),/配置及今日判断已更新/);
  assert.equal(await page.locator('#strategyCapitalAction input').isVisible(),false);
  const text=await page.locator('#strategyMonthlyTarget').innerText();
  assert.match(text,/卖出 1 股/);assert.match(text,/买入 9 股/);
  assert.doesNotMatch(text,/上一条建议/);
  await page.screenshot({path:process.argv[2]+'/capital-ready.png',fullPage:true});
  await page.reload();
  await page.waitForFunction(()=>window.RealStrategyCapital&&!realStrategyInitializing&&
    !realStrategyHeaderRefreshing&&!RealStrategyDaily.getState().busy);
  const reloaded=await page.evaluate(()=>RealStrategyDaily.getState());
  assert.equal(reloaded.account.revision,after.account.revision);
  assert.equal(reloaded.account.available_cash,'3100');
  assert.equal(reloaded.target.target_id,after.target.target_id);
  assert.equal(reloaded.daily.status,'READY');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'CAPITAL_BROWSER_ARCHIVED_RUNTIME_PASS',cash:after.account.available_cash,
   target_id:after.target.target_id,account_revision:after.account.revision,page_errors:errors,
   production_html_unmodified:true,reload_preserved:true,duplicate_submit:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class FullPageCapitalTests(fixture.CapitalBrowserTests):
    # Full-page startup previews the old target before the deposit, then the
    # new account revision/target needs its own bound supplement. Re-reads of
    # either completed snapshot must not cause a third capture.
    expected_supplement_captures = ['AAA', 'AAA']
    def advice_application(self, context, risk_reader):
        if not hasattr(context, 'browser_app'):
            # The substituted V23 base must retain its production live binding.
            # The parent fixture's context.target is updated only after the
            # browser returns, so it cannot serve in-flight capital publication.
            risk_reader.source_reader.account_reader = context.capital_monthly.accounts.read
            risk_reader.source_reader.target_reader = context.capital_monthly.current
            context.browser_app = v24.FillHandoffHTTPTests.advice_application(self, context, risk_reader)
        return context.browser_app

    def perform_contribution(self, context, client, body):
        app = self.advice_application(context, context.risk_reader)
        app.include_router(create_router(service=context.capital_monthly))
        app.mount('/static', StaticFiles(directory=fixture.ROOT/'web'), name='static')
        @app.get('/')
        def page():
            return FileResponse(fixture.ROOT/'web/index.html', media_type='text/html')
        proxy = FastAPI()
        proxy.mount('/', app)
        counts = dict(arrive=0, configure=0, preview=0)
        @proxy.middleware('http')
        async def count_and_advance(request, call_next):
            for key, path in [('arrive','/api/strategy-capital-v2/arrive'),
                              ('configure','/api/strategy-capital-v2/configure'),
                              ('preview','/api/strategy-daily-v3/preview')]:
                if request.url.path == path:
                    counts[key] += 1
                    if key == 'preview':context.clock[0] += timedelta(minutes=1)
            return await call_next(request)
        output = fixture.ROOT/'tmp'/('full_page_capital_'+uuid4().hex[:8])
        output.mkdir()
        before = context.store.read()
        listener = socket.socket();listener.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(proxy, log_level='error'))
        thread = threading.Thread(target=lambda:server.run(sockets=[listener]), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(server.started)
            result = subprocess.run([str(fixture.NODE), '-e', BROWSER,
                'http://127.0.0.1:'+str(listener.getsockname()[1]), str(output), context.clock[0].isoformat(), json.dumps(body)],
                capture_output=True, text=True, encoding='utf-8', timeout=90)
            (output/'browser.log').write_text(result.stdout+result.stderr, encoding='utf-8')
            (output/'http-counts.json').write_text(json.dumps(counts), encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(counts['arrive'], 1);self.assertEqual(counts['configure'], 1)
            after = context.store.read()
            self.assertEqual(after['available_cash'], '3100')
            self.assertEqual(after['shares'], before['shares'])
            self.assertEqual(after['orders'], before['orders'])
            self.browser_receipt = json.loads(result.stdout)
            self.browser_receipt.update(http_counts=counts, isolated=True, production_account_writes=False)
            (output/'result.json').write_text(json.dumps(self.browser_receipt, indent=2), encoding='utf-8')
            print('FULL_PAGE_CAPITAL_ACCEPTANCE='+str(output))
        finally:
            server.should_exit=True;thread.join(timeout=10);listener.close()
            self.assertFalse(thread.is_alive())
