'use strict';
const assert=require('node:assert/strict');
const {wrap}=require('../web/strategy_display_batch_fetch.js');
const {mount}=require('../web/strategy_monthly_target_charts.js');
const path=(id,interval='day',proposal='p')=>`/api/strategy-display/latest-bars?security_id=${id}&expected_proposal_id=${proposal}&interval=${interval}&bars=260`;
const chart=id=>({status:'DISPLAY_ONLY',executable:false,proposal_id:'p',security_id:id,ticker:id,
 account_revision:'r',target_id:'t',bars:[{complete:true,close:11}],price:11});
function reply(ids){return {ok:true,status:200,json:async()=>({status:'DISPLAY_ONLY',executable:false,proposal_id:'p',charts:ids.map(chart)})};}
(async()=>{
 let calls=[];
 const fetch=wrap(async(url,options)=>{calls.push({url,options});return reply(['A','B']);});
 const results=await Promise.all([fetch(path('A')),fetch(path('B'))]);
 assert.equal(calls.length,1);
 assert(calls[0].url.startsWith('/api/strategy-display/latest-batch?'));
 assert.equal((await results[0].json()).security_id,'A');
 assert.equal((await results[1].json()).security_id,'B');
 assert.equal(calls[0].options.cache,'no-store');
 await Promise.all([fetch(path('A','week')),fetch(path('B','day'))]);
 assert.equal(calls.length,3,'different periods must not merge');
 assert(calls.slice(1).every(call=>call.url.includes('latest-bars?')));
 await Promise.all([fetch(path('A','day','p1')),fetch(path('B','day','p2'))]);
 assert.equal(calls.length,5,'different proposals must not merge');

 let release,transportSignal;
 const aborting=wrap((url,options)=>{transportSignal=options.signal;return new Promise(resolve=>release=resolve);});
 const a=new AbortController(),b=new AbortController();
 const first=aborting(path('A'),{signal:a.signal});
 const second=aborting(path('B'),{signal:b.signal});
 const rejected=assert.rejects(first,{name:'AbortError'});
 await Promise.resolve();a.abort();await rejected;
 assert.equal(transportSignal.aborted,false,'one period change cannot cancel another chart');
 release(reply(['A','B']));
 assert.equal((await (await second).json()).security_id,'B');

 let bothSignal;
 const cancelAll=wrap((url,options)=>{bothSignal=options.signal;return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))));});
 const c=new AbortController(),d=new AbortController();
 const all=Promise.allSettled([cancelAll(path('A'),{signal:c.signal}),cancelAll(path('B'),{signal:d.signal})]);
 await Promise.resolve();c.abort();d.abort();await all;
 assert.equal(bothSignal.aborted,true);

 const malformed=wrap(async()=>reply(['A','A']));
 const invalid=await Promise.allSettled([malformed(path('A')),malformed(path('B'))]);
 assert(invalid.every(item=>item.status==='rejected'&&item.reason.message==='DISPLAY_BATCH_INVALID'));

 let loader,finish,requests=0,created=0;
 const component=mount({container:{replaceChildren(){}},latestDisplayEnabled:true,
  fetchImpl:wrap(async()=>{requests++;return new Promise(resolve=>finish=resolve);}),
  createCharts:(node,load)=>{created++;loader=load;return {destroy(){},setSelection(){}};}});
 component.setAccount({revision:'r',holdings:[]});
 const target={target_id:'t',proposal_id:'p',targets:[{security_id:'A',ticker:'A',quantity:1},{security_id:'B',ticker:'B',quantity:1}]};
 component.setTarget(target);
 const initial=Promise.all([loader('A','day'),loader('B','day')]);
 await Promise.resolve();finish(reply(['A','B']));
 assert((await initial).every(value=>value.display_only));
 assert.equal(requests,1);
 const old=Promise.allSettled([loader('A','day'),loader('B','day')]);
 await Promise.resolve();const priorCreated=created;component.setAccount({revision:'new',holdings:[]});finish(reply(['A','B']));
 assert.equal(created,priorCreated+1,'cash-only revision change must recreate charts');
 assert((await old).every(item=>item.status==='rejected'&&/CHART_CHANGED/.test(item.reason.message)));
 component.destroy();
 console.log('PASS batching, period/proposal separation, independent cancellation, malformed response and stale account rejection');
})().catch(error=>{console.error(error);process.exitCode=1;});
