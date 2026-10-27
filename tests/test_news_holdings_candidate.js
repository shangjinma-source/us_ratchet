const assert=require('node:assert/strict');
const h=require('../web/news.js');
const payload={status:'SAVED_TARGET',target_id:'a'.repeat(64),proposal_id:'b'.repeat(64),target_month:'2026-10',server_month:'2026-10',proposal_targets:[{security_id:'sid:1',ticker:'MRNA',quantity:52},{security_id:'sid:2',ticker:'SNDK',quantity:10}],risk_monthly_targets:{'sid:1':52,'sid:2':10}};
const targets=h.targetSnapshot(payload),held={known:true,tickers:['SNDK']};
assert.equal(targets.known,true);
const events=[{id:1,tickers:['NVDA']},{id:2,tickers:['MRNA']},{id:3,tickers:['SNDK']},{id:4,tickers:['MRNA']}];
assert.deepEqual(h.orderedEvents(events,held,targets).map(e=>e.id),[3,2,4,1]);
assert.match(h.targetLabel(events[1],targets),/非当前买入建议/);
assert.match(h.relationLabel(events[1],held),/非已录持仓/);
for(const patch of [{status:'BLOCKED'},{server_month:'2026-11'},{proposal_targets:undefined},{proposal_id:null},{risk_monthly_targets:{'sid:1':51,'sid:2':10}},{risk_monthly_targets:{'sid:1':52,'sid:2':10,'sid:3':5}}]) assert.equal(h.targetSnapshot({...payload,...patch}).known,false);
assert.equal(h.targetSnapshot({...payload,targets:payload.proposal_targets,proposal_targets:undefined}).known,false,'no original-target fallback');
assert.equal(h.targetSnapshot({...payload,proposal_targets:[{security_id:'sid:1',ticker:'MRNA',quantity:0}],risk_monthly_targets:{'sid:1':0}}).rows.length,0);
assert.match(h.targetCoverageLabels(events,targets)[0],/无正文/);
assert.match(h.targetCoverageLabels([],h.targetSnapshot(null))[0],/未知/);
console.log('PASS target contract, month validity, proposal binding, no original-target fallback, held/target priority, zero quantity, body gap');

{
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path='../web/news.js';
const h=require(path);
const held=h.holdingsSnapshot({status:'READY',account:{holdings:[{ticker:'SNDK',quantity:14}]}});
const events=[{id:'other',tickers:['MRNA'],content_kind:'ISSUER_RELEASE_BODY',source_text:'body'}, {id:'macro',tickers:[],relevance:'macro'}, {id:'held',tickers:['SNDK'],content_kind:'SEC_METADATA_ONLY',source_text:'metadata',analysis_status:'ANALYZED'}];
assert.deepEqual(h.orderedEvents(events,held).map(e=>e.id),['held','other','macro']);
assert.deepEqual(events.map(e=>e.id),['other','macro','held']);
assert.match(h.relationLabel(events[0],held),/非已录持仓/);
assert.match(h.relationLabel(events[1],held),/宏观/);
assert.match(h.coverageLabels(events,held)[0],/无公告正文/);
assert.equal(h.hasBody({...events[2],content_kind:'RSS_EXCERPT'}),false);
assert.equal(h.hasBody({...events[2],content_kind:'ISSUER_RELEASE_BODY',source_text:''}),false);
assert.equal(h.hasBody(events[0]),true);
assert.equal(h.holdingsSnapshot(null).known,false);
assert.equal(h.holdingsSnapshot({status:'NOT_INITIALIZED'}).known,false);
assert.match(h.coverageLabels([],h.holdingsSnapshot(null))[0],/不可用/);
const partial=h.holdingsSnapshot({status:'READY',account:{holdings:[{ticker:null,quantity:14}]}});
assert.equal(partial.unresolved,1);
assert.match(h.relationLabel(events[0],partial),/不能完整确认/);
assert.match(h.coverageLabels([],partial)[0],/覆盖未知/);
assert.match(h.coverageLabels([],h.holdingsSnapshot({status:'READY',account:{holdings:[]}}))[0],/未记录持仓/);
async function integration(){
 const nodes={},calls=[];let accountFails=false;
 function node(){return {disabled:false,childElementCount:0,textContent:'',children:[],addEventListener(t,f){const previous=this[t];this[t]=async()=>{if(previous)await previous();await f();};},append(...v){this.children.push(...v);this.childElementCount=this.children.length;},replaceChildren(...v){this.children=v;this.childElementCount=v.length;}};}
 const context={document:{getElementById(id){if(id==='history-content')return null;return nodes[id] ||=node();},createElement:node},URL,Date,AbortController,console,setTimeout(fn,ms){if(ms===3000)queueMicrotask(fn);return 1;},clearTimeout(){},async fetch(url,options){calls.push({url,options});if(url==='/api/strategy-account'){if(accountFails)throw Error('unavailable');return {ok:true,json:async()=>({status:'READY',account:{holdings:[{ticker:'SNDK',quantity:14}],cash:'DO_NOT_SEND'}})};}if(url==='/api/news/refresh')return {status:202};if(url==='/api/news/job')return {ok:true,json:async()=>({status:'SUCCEEDED'})};return {ok:true,json:async()=>({schema_version:'news-desk-v1',events})};}};
 vm.runInNewContext(fs.readFileSync(require.resolve(path),'utf8'),context);
 await new Promise(setImmediate);
 assert.equal(calls.length,3);assert(calls.every(c=>c.options.method==='GET'));
 accountFails=true;await nodes.refresh.click();
 const text=JSON.stringify(nodes['holdings-coverage']);assert.match(text,/不可用/);
 await nodes.analyze.click();
 const posts=calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,1);assert.equal(posts[0].options.body,'{}');assert.equal(posts[0].url,'/api/news/refresh');
 assert(!JSON.stringify(posts).includes('DO_NOT_SEND'));
 console.log('PASS: holdings stable priority, unknown/partial/empty distinction, body coverage, account-failure reset, GET-only load and unchanged explicit model body');
}
integration().catch(e=>{console.error(e);process.exitCode=1;});

}
