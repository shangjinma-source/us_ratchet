'use strict';
// Isolated browser; all account writes are intercepted, only preview POST reaches server.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const directory=process.argv[2];assert(directory,'Output directory required');fs.mkdirSync(directory);
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{const page=await browser.newPage({viewport:{width:1600,height:1100}});let baseline=null,cashPosts=0;const unexpected=[];
 const requests=new Map(),network=[],previewResponses=[],responseReads=[];
 page.on('response',response=>{
  const path=new URL(response.url()).pathname;
  if(path!=='/api/strategy-daily-v3/preview')return;
  responseReads.push((async()=>{
   const entry={path,http_status:response.status(),observed_at:new Date().toISOString()};
   try{entry.body=await response.json();}catch{entry.body_unavailable=true;}
   previewResponses.push(entry);
  })());
 });
 page.on('request',request=>{
  const path=new URL(request.url()).pathname;
  if(path.startsWith('/api/'))requests.set(request,{path,method:request.method(),started_at:new Date().toISOString(),start:performance.now()});
 });
 const finished=(request,failed)=>{
  const entry=requests.get(request);if(!entry)return;
  requests.delete(request);
  const {start,...publicEntry}=entry;
  network.push({...publicEntry,elapsed_ms:Math.round(performance.now()-start),failed});
 };
 page.on('requestfinished',request=>finished(request,false));
 page.on('requestfailed',request=>finished(request,true));
 await page.route('**/*',async route=>{const req=route.request(),path=new URL(req.url()).pathname;
  if(req.method()==='POST'&&path==='/api/strategy-account/events'){
   assert.equal(req.postDataJSON().event.kind,'CASH_CONFIRM');assert(baseline);cashPosts++;
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(baseline)});
  }
  if(req.method()!=='GET'&&path!=='/api/strategy-daily-v3/preview'){unexpected.push(path);return route.abort();}
  return route.continue();
 });
 await page.goto('http://127.0.0.1:8010/',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>window.RealStrategyDaily&&!RealStrategyDaily.getState().busy&&(RealStrategyDaily.getState().daily||RealStrategyDaily.getState().error)&&!document.getElementById('btnRefresh').disabled,null,{timeout:240000});
 baseline=await page.evaluate(async()=>await(await fetch('/api/strategy-account',{cache:'no-store'})).json());
 await page.getByRole('button',{name:'更新现金并查看建议',exact:true}).click();await page.evaluate(()=>RealStrategyDaily.whenIdle());
 const capture=await page.evaluate(()=>{
  const state=RealStrategyDaily.getState(),presentation=StrategyDailyController.presentation(state);
  const domRows=[...document.querySelectorAll('#strategyMonthlyTarget table tr')].filter(row=>row.querySelector('td'));
  const visible_rows=presentation.rows.map(row=>{
   const matches=domRows.filter(dom=>dom.querySelector('td')?.textContent===(row.ticker||row.security_id));
   const cells=matches.length===1?[...matches[0].querySelectorAll('td')].map(cell=>cell.textContent.trim()):[];
   return {...row,dom_match_count:matches.length,dom_cells:cells,explanation:cells[6]||''};
  });
  const table_headers=[...document.querySelectorAll('#strategyMonthlyTarget table th')].map(cell=>cell.textContent.trim());
  return {observed_at:new Date().toISOString(),state,visible_rows,table_headers,page_text:document.body.innerText};
 });
 capture.account_before=baseline.account;capture.account_after=(await page.evaluate(async()=>await(await fetch('/api/strategy-account',{cache:'no-store'})).json())).account;
 capture.cash_posts_intercepted=cashPosts;capture.unexpected_writes=unexpected;
 await Promise.all(responseReads);
 capture.network_timings=network;
 capture.preview_responses=previewResponses;
 capture.scope='Actual served cash button and real preview; cash acknowledgement intercepted; no real account write';
 fs.writeFileSync(directory+'/capture.json',JSON.stringify(capture,null,2));await page.screenshot({path:directory+'/page.png',fullPage:true});
 console.log(JSON.stringify({captured:true,status:capture.state.daily?.status??null,reason:capture.state.daily?.reason??capture.state.error??null,preview_http_status:previewResponses.at(-1)?.http_status??null,directory}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
