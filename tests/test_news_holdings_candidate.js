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
 function node(){return {disabled:false,childElementCount:0,textContent:'',children:[],addEventListener(t,f){this[t]=f;},append(...v){this.children.push(...v);this.childElementCount=this.children.length;},replaceChildren(...v){this.children=v;this.childElementCount=v.length;}};}
 const context={document:{getElementById(id){return nodes[id] ||=node();},createElement:node},URL,Date,AbortController,console,setTimeout(fn,ms){if(ms===3000)queueMicrotask(fn);return 1;},clearTimeout(){},async fetch(url,options){calls.push({url,options});if(url==='/api/strategy-account'){if(accountFails)throw Error('unavailable');return {ok:true,json:async()=>({status:'READY',account:{holdings:[{ticker:'SNDK',quantity:14}],cash:'DO_NOT_SEND'}})};}if(url==='/api/news/refresh')return {status:202};if(url==='/api/news/job')return {ok:true,json:async()=>({status:'SUCCEEDED'})};return {ok:true,json:async()=>({schema_version:'news-desk-v1',events})};}};
 vm.runInNewContext(fs.readFileSync(require.resolve(path),'utf8'),context);
 await new Promise(setImmediate);
 assert.equal(calls.length,2);assert(calls.every(c=>c.options.method==='GET'));
 accountFails=true;await nodes.refresh.click();
 const text=JSON.stringify(nodes['holdings-coverage']);assert.match(text,/不可用/);
 await nodes.analyze.click();
 const posts=calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,1);assert.equal(posts[0].options.body,'{}');assert.equal(posts[0].url,'/api/news/refresh');
 assert(!JSON.stringify(posts).includes('DO_NOT_SEND'));
 console.log('PASS: holdings stable priority, unknown/partial/empty distinction, body coverage, account-failure reset, GET-only load and unchanged explicit model body');
}
integration().catch(e=>{console.error(e);process.exitCode=1;});
