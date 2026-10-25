"""Unmodified production HTML and mounts, isolated V24 ledger and market fixture."""
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
import test_account_fill_advice_handoff_browser as component


def full_page_browser():
    code = component.BROWSER
    start = code.index('  await page.evaluate(async now=>{')
    end = code.index('  const original=', start)
    code = code[:start] + """
  await page.waitForFunction(()=>window.RealStrategyDaily&&window.RealStrategyAccount&&
    !realStrategyInitializing&&!realStrategyHeaderRefreshing&&!RealStrategyDaily.getState().busy);
  await page.evaluate(()=>{window.daily=RealStrategyDaily;window.account=RealStrategyAccount;});
""" + code[end:]
    code = code.replace("await page.goto(process.argv[1]);",
        "await page.clock.install({time:new Date(process.argv[3])});await page.goto(process.argv[1]);")
    code = code.replace("  const form=page.locator", "  await page.getByText('操作与持仓',{exact:true}).click();\n  const form=page.locator")
    code = code.replace('#account-panel', '#realStrategyAccount').replace('#daily-panel', '#strategyMonthlyTarget')
    code = code.replace("  await page.locator('#strategyMonthlyTarget input[name=amount]')",
        "  await page.getByText('今日建议',{exact:true}).click();\n  await page.locator('#strategyMonthlyTarget input[name=amount]')")
    code = code.replace('  console.log(JSON.stringify', """
  const sell=final.daily.new_orders.find(row=>row.side==='SELL');assert.ok(sell);
  const sellTicker=final.account.holdings.find(row=>row.security_id===sell.security_id).ticker;
  await page.getByText('操作与持仓',{exact:true}).click();
  const sellForm=page.locator('#realStrategyAccount form[data-form="fill"]');
  await sellForm.locator('[name=ticker]').fill(sellTicker);
  await sellForm.locator('[name=side]').selectOption('SELL');
  await sellForm.locator('[name=quantity]').fill(String(sell.quantity));
  await sellForm.locator('[name=price]').fill(String(fraction(sell.limit_price)));
  await sellForm.locator('[name=executed_at]').fill(time);
  await sellForm.getByRole('button',{name:'保存真实成交'}).click();
  await page.waitForFunction(()=>!account.getState().busy&&account.getState().message==='成交已记录。');
  await page.waitForFunction(()=>!daily.getState().busy&&daily.getState().account?.revision===account.getState().account?.revision);
  assert.equal(await page.evaluate(()=>daily.getState().daily),null);
  const afterSellCash=cash+sell.quantity*fraction(sell.limit_price);
  await page.getByText('今日建议',{exact:true}).click();
  await page.locator('#strategyMonthlyTarget input[name=amount]').fill(String(afterSellCash));
  await page.getByRole('button',{name:'更新现金并查看建议',exact:true}).click();
  await page.evaluate(()=>daily.whenIdle());
  const sold=await page.evaluate(()=>daily.getState());
  assert.equal(sold.daily.status,'READY');
  assert.ok(!sold.daily.new_orders.some(row=>row.security_id===sell.security_id&&row.side==='SELL'));
  assert.equal(sold.target.target_id,original.target.target_id);
  const revision=sold.account.revision;
  await page.reload();
  await page.waitForFunction(()=>window.RealStrategyDaily&&!realStrategyInitializing&&
    !realStrategyHeaderRefreshing&&!RealStrategyDaily.getState().busy);
  const reloaded=await page.evaluate(()=>RealStrategyDaily.getState());
  assert.equal(reloaded.account.revision,revision);
  assert.equal(reloaded.target.target_id,original.target.target_id);
  assert.equal(reloaded.daily.status,'READY');
  assert.ok(!reloaded.daily.new_orders.some(row=>row.security_id===sell.security_id&&row.side==='SELL'));
  assert.equal(reloaded.daily.new_orders.find(row=>row.security_id===buy.security_id&&row.side==='BUY').quantity,remaining.quantity);
  assert.equal(reloaded.account.fills.length,original.account.fills.length+2);
  const clearedRow=page.locator('#strategyMonthlyTarget tr').filter({hasText:sellTicker});
  assert.equal(await clearedRow.count(),1);
  assert.match(await clearedRow.innerText(),/空仓，无需操作/);
  assert.match(await clearedRow.innerText(),/当前空仓，今日无需买卖/);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:process.argv[2]+'/after-sell-reload.png',fullPage:true});
  console.log(JSON.stringify""")
    code = code.replace('isolated:true}', 'isolated:true,production_html_unmodified:true,sold:sell.quantity,after_sell_cash:afterSellCash,no_repeat_sell:true,reload_preserved:true}')
    return code


class FullPageFillHandoffTests(component.fixture.FillHandoffHTTPTests):
    def verify_fill_handoff(self, context, risk_reader):
        app = context.capital_application
        app.include_router(create_router(service=context.capital_monthly))
        app.mount('/static', StaticFiles(directory=component.ROOT/'web'), name='static')

        @app.get('/')
        def page():
            return FileResponse(component.ROOT/'web/index.html', media_type='text/html')

        proxy = FastAPI()
        proxy.mount('/', app)

        @proxy.middleware('http')
        async def advance_fixture_quote(request, call_next):
            if request.url.path == '/api/strategy-daily-v3/preview':
                context.clock[0] += timedelta(minutes=1)
            return await call_next(request)

        output = component.ROOT/'tmp'/('full_page_fill_handoff_'+uuid4().hex[:8])
        output.mkdir()
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
            result = subprocess.run([str(component.NODE), '-e', full_page_browser(),
                'http://127.0.0.1:'+str(listener.getsockname()[1]), str(output),
                context.clock[0].isoformat()], capture_output=True, text=True,
                encoding='utf-8', timeout=90)
            (output/'browser.log').write_text(result.stdout+result.stderr, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['status'], 'PASS')
            (output/'result.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print('FULL_PAGE_ACCEPTANCE='+str(output))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            self.assertFalse(thread.is_alive())
