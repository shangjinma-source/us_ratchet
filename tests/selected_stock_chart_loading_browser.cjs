const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();await page.setContent('<div id="chart"></div>');
  await page.addScriptTag({path:path.resolve('web/selected_stock_charts.js')});
  await page.evaluate(()=>{
   window.IntersectionObserver=undefined;
   window.chart=SelectedStockCharts.createSelectedStockCharts(document.querySelector('#chart'),()=>new Promise(resolve=>window.completeChart=resolve));
   chart.setSelection({monthly_target:true,stocks:[{ticker:'AAA',security_id:'A',quantity:1}]});
   chart.setFills([{ticker:'AAA',security_id:'A',quantity:1,side:'BUY',price:12,executed_at:'2026-10-16T15:00:00Z'}]);
  });
  const note=page.getByLabel('AAA 真实成交标记');assert.equal(await note.innerText(),'');
  await page.evaluate(()=>completeChart({ticker:'AAA',status:'AVAILABLE',daily_as_of:'2026-10-14',bars:[{date:'2026-10-14',open:10,high:13,low:9,close:12,volume:1}]}));
  await page.waitForFunction(()=>document.body.innerText.includes('成交在当前历史区间外'));
  await page.getByRole('button',{name:'周线',exact:true}).click();assert.equal(await note.innerText(),'');
  console.log('PASS loading has no false fill warning, completed data reports actual outside fill, period switch clears old warning');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
