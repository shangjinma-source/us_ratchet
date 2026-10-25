"""Real browser forms against isolated V24 API/ledger; fixture market only."""
import json
import socket
import subprocess
import threading
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from api.strategy_monthly_target import create_router
import test_account_fill_advice_handoff_http as fixture
from test_cash_button_real_ledger_browser import NODE

ROOT = Path(__file__).resolve().parents[1]
BROWSER = r"""
const assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(process.argv[1]);
  await page.evaluate(async now=>{
   window.account=StrategyAccountUI.mount({container:document.getElementById('account-panel'),initialValuation:false,
    automaticValuationEnabled:false,onInvalidate:()=>window.daily?.accountInvalidated(),
    onRender:(_,state)=>{if(state.loaded&&!state.busy&&window.daily&&!daily.getState().busy)daily.load();}});
   await account.ready;
   const request=StrategyDailyController.fetchTransport(fetch.bind(window));
   window.daily=StrategyDailyMount.mount(document.getElementById('daily-panel'),{
    ...StrategyDailyController.httpDependencies(request,()=>crypto.randomUUID(),account),now:()=>Date.parse(now),
    onRecommendedTickers:tickers=>account.setRecommendedTickers(tickers)});
   await daily.ready;await daily.refresh();
  },process.argv[3]);
  const original=await page.evaluate(()=>daily.getState());
  assert.equal(original.daily.status,'READY');
  const buy=original.daily.new_orders.find(o=>o.side==='BUY');assert.ok(buy.quantity>1);
  const ticker=original.target.targets.find(r=>r.security_id===buy.security_id).ticker;
  const fraction=s=>{const p=String(s).split('/');return Number(p[0])/(p[1]?Number(p[1]):1);};
  const quantity=Math.floor(buy.quantity/2),price=fraction(buy.limit_price);
  const form=page.locator('#account-panel form[data-form="fill"]');
  await form.locator('[name=ticker]').fill(ticker);await form.locator('[name=side]').selectOption('BUY');
  await form.locator('[name=quantity]').fill(String(quantity));await form.locator('[name=price]').fill(String(price));
  const time=new Date(Date.parse(process.argv[3])+8*3600000).toISOString().slice(0,16);
  await form.locator('[name=executed_at]').fill(time);await form.getByRole('button',{name:'保存真实成交'}).click();
  await page.waitForFunction(()=>account.getState().message==='成交已记录。'&&!account.getState().busy);
  await page.waitForFunction(()=>!daily.getState().busy&&daily.getState().account?.revision===account.getState().account?.revision);
  const after=await page.evaluate(()=>daily.getState());
  assert.equal(after.account.cash_confirmation_valid,false);assert.equal(after.daily,null);
  const held=after.account.holdings.find(r=>r.security_id===buy.security_id);
  assert.equal(held.quantity,quantity+(original.account.holdings.find(r=>r.security_id===buy.security_id)?.quantity||0));
  await page.screenshot({path:process.argv[2]+'/after-fill.png',fullPage:true});
  const cash=fraction(original.account.available_cash)-quantity*price;
  await page.locator('#daily-panel input[name=amount]').fill(String(cash));
  await page.getByRole('button',{name:'更新现金并查看建议',exact:true}).click();await page.evaluate(()=>daily.whenIdle());
  const final=await page.evaluate(()=>daily.getState());assert.equal(final.error,null);assert.equal(final.daily.status,'READY');
  const remaining=final.daily.new_orders.find(o=>o.side==='BUY'&&o.security_id===buy.security_id);
  assert.equal(remaining.quantity,buy.quantity-quantity);assert.equal(final.target.target_id,original.target.target_id);
  assert.equal(final.daily.account_revision,final.account.revision);assert.deepEqual(errors,[]);
  assert.match(await page.locator('#daily-panel').innerText(),new RegExp('买入.*'+remaining.quantity+' 股'));
  await page.screenshot({path:process.argv[2]+'/remaining-advice.png',fullPage:true});
  console.log(JSON.stringify({status:'PASS',before_buy:buy.quantity,filled:quantity,remaining_buy:remaining.quantity,
   cash,old_advice_invalidated:true,page_errors:errors,isolated:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
"""

class FillHandoffBrowserTests(fixture.FillHandoffHTTPTests):
    def verify_fill_handoff(self,c,risk_reader):
        app=c.capital_application
        app.include_router(create_router(service=c.capital_monthly))
        scripts=('strategy_account.js','strategy_daily_controller.js','strategy_daily_mount.js')
        proxy=FastAPI()
        proxy.mount('/',app)
        @proxy.middleware('http')
        async def advance_fixture_quote(request,call_next):
            if request.url.path=='/api/strategy-daily-v3/preview':c.clock[0]+=timedelta(minutes=1)
            return await call_next(request)
        @app.get('/')
        def page():
            return HTMLResponse('<meta charset="utf-8"><style>body{font:16px sans-serif;padding:20px}td,th{padding:12px}input,button{padding:8px}</style><div id="daily-panel"></div><div id="account-panel"></div>'+''.join('<script src="/web/'+s+'"></script>' for s in scripts))
        @app.get('/web/{name}')
        def script(name:str):
            if name not in scripts:raise ValueError('unexpected asset')
            return FileResponse(ROOT/'web'/name,media_type='text/javascript')
        output=ROOT/'tmp'/('fill_handoff_browser_'+uuid4().hex[:8]);output.mkdir()
        listener=socket.socket();listener.bind(('127.0.0.1',0))
        server=uvicorn.Server(uvicorn.Config(proxy,log_level='error'))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(server.started)
            result=subprocess.run([str(NODE),'-e',BROWSER,'http://127.0.0.1:'+str(listener.getsockname()[1]),str(output),c.clock[0].isoformat()],capture_output=True,text=True,encoding='utf-8',timeout=90)
            (output/'browser.log').write_text(result.stdout+result.stderr,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            receipt=json.loads(result.stdout);self.assertEqual(receipt['status'],'PASS')
            (output/'result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            print('BROWSER_ACCEPTANCE='+str(output))
        finally:
            server.should_exit=True;thread.join(timeout=10);listener.close()
            self.assertFalse(thread.is_alive())
