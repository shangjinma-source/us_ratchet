const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const Module = require('node:module');
const filename = path.resolve(__dirname, '../web/news_investment_review.js');
const source = fs.readFileSync(process.env.NEWS_EVENT_UI_CANDIDATE || filename, 'utf8');
if (!source.includes('/api/news/events/status')) { console.log('SKIP: event candidate not released'); process.exit(0); }
const loaded = new Module(filename, module); loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(path.dirname(filename)); loaded._compile(source, filename);
class Element {
 constructor(tag, doc) { this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={}; }
 appendChild(child) { this.children.push(child); }
 replaceChildren(...children) { this.children=children; }
 addEventListener(name, callback) { this.listeners[name]=callback; }
 removeEventListener(name) { delete this.listeners[name]; }
}
const document = {createElement(tag) { return new Element(tag, document); }};
const flat = node => [node,...node.children.flatMap(flat)];
const settle = async () => { for(let count=0;count<15;count++) await Promise.resolve(); };
(async()=>{
 const host = new Element('div', document), requests=[], timers=new Map();let enabled=false,id=0;
 const instance=loaded.exports.mount(host, {
  fetch:async(url,options)=>{requests.push({url,options});if(options){assert.equal(url,'/api/news/events/control');enabled=JSON.parse(options.body).enabled;}
   return {ok:true,json:async()=>({enabled,status:enabled?'WAITING':'DISABLED',unsupported_tickers:['OTHER']})};},
  setTimer:(callback, milliseconds)=>{timers.set(++id,{callback,milliseconds});return id;},clearTimer:key=>timers.delete(key)
 });
 await settle();assert.equal(requests.length,1);assert.equal(requests[0].options,undefined);
 assert.equal(requests[0].url,'/api/news/events/status');
 const toggle=flat(host).find(node=>node.textContent==='开启新事件发现');assert.ok(toggle);
 await toggle.listeners.click();await settle();assert.equal(toggle.textContent,'关闭新事件发现');
 assert.equal(requests.filter(row=>row.options).length,1);
 assert.ok(flat(host).some(node=>(node.textContent||'').includes('部分股票尚无来源覆盖')));
 const scheduled=[...timers.values()];assert.equal(scheduled.length,1);assert.equal(scheduled[0].milliseconds,15000);
 timers.clear();await scheduled[0].callback();await settle();
 assert.equal(requests.filter(row=>row.options).length,1,'status polling never starts a model');
 instance.dispose();assert.equal(timers.size,0);assert.equal(toggle.listeners.click,undefined);
 const now=Date.parse('2026-10-28T13:31:00Z');
 const proposal={review_id:'j',status:'REVIEW_PROPOSAL_ONLY',executable:false,orders_created:false,rows:[],
  original_binding:{account_revision:'a',target_id:'t',proposal_id:'p'},review_valid_until:'2026-10-28T13:35:00Z',
  timeliness:{mode:'EVENT_SOURCE_PREANALYSIS_FINALIZED',source_discovered_at:'2026-10-28T10:00:00Z',first_execution_window:{not_before:'2026-10-28T13:30:00Z'}}};
 assert.equal(loaded.exports.eventTiming(proposal),'盘前已发现 · 首个交易窗口复核');
 for(const late of [false,true]){
  const secondHost=new Element('div',document);let on=true,current=null,resolveJob;
  const pending=new Promise(resolve=>{resolveJob=resolve;});
  const second=loaded.exports.mount(secondHost,{now:()=>now,onReviewChange:value=>{current=value.proposal;},
   setTimer:()=>1,clearTimer:()=>{},fetch:async(url,options)=>{
    if(options){on=JSON.parse(options.body).enabled;return {ok:true,json:async()=>({enabled:on})};}
    if(url.includes('/job?')){if(late)await pending;return {ok:true,json:async()=>({status:'COMPLETE',job_id:'j',proposal})};}
    return {ok:true,json:async()=>({status:'REVIEW_COMPLETE',enabled:on,job_id:'j'})};
   }});
  second.update({account:{revision:'a'},target:{target_id:'t',proposal_id:'p'},daily:{status:'READY',account_revision:'a',target_id:'t',proposal_id:'p'}});
  await settle();if(!late)assert.ok(current);
  const close=flat(secondHost).find(node=>node.textContent==='关闭新事件发现');assert.ok(close);
  const closing=close.listeners.click();assert.equal(current,null,'closing clears event opinion immediately');
  resolveJob();await closing;await settle();assert.equal(current,null,'late complete cannot resurrect disabled event');
  second.dispose();
 }
 console.log('PASS: status-only polling, explicit control, coverage warning, dispose cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});
