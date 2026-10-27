const assert=require('node:assert/strict');
const ui=require('../web/news_investment_review.js');
class Node{constructor(doc){this.ownerDocument=doc;this.children=[];this.listeners={};}appendChild(n){this.children.push(n);}replaceChildren(...n){this.children=n;}addEventListener(k,f){this.listeners[k]=f;}removeEventListener(k){delete this.listeners[k];}}
const doc={createElement:()=>new Node(doc)};
const state={account:{revision:'r',holdings:[]},target:{target_id:'t',proposal_id:'p'},daily:{status:'READY',account_revision:'r',target_id:'t',proposal_id:'p',reference_quotes:{A:{sell:10}}}};
const proposal={status:'REVIEW_PROPOSAL_ONLY',original_binding:{target_id:'t',proposal_id:'p',account_revision:'r'},review_created_at:'2026-10-27T00:00:00Z',review_valid_until:'2026-10-27T00:05:00Z',orders_created:false,executable:false,rows:[{security_id:'A',action:'EXIT',reason:'<script>bad()</script>',original_target_quantity:2,evidence:[{url:'javascript:alert(1)',published_at:'2026-10-26T22:00:00Z',observed_at:'2026-10-27T00:00:00Z',publication_age_seconds:7200,discovery_delay_seconds:7200}]}]};
(async()=>{
 const clock=Date.parse('2026-10-27T00:01:00Z');assert.equal(ui.view(state,proposal,clock).valid,true);assert.equal(ui.view(state,proposal,clock+300000).valid,false);assert.equal(ui.safeUrl('javascript:x'),null);
 let calls=[],resolve;const instance=ui.mount(new Node(doc),{now:()=>clock,fetch:async(url,options)=>{calls.push([url,options]);return new Promise(r=>{resolve=r;});},setTimer:()=>1,clearTimer:()=>{}});
 instance.update(state);assert.equal(calls.length,0);const pending=instance.start();assert.equal(calls.length,1);assert.deepEqual(JSON.parse(calls[0][1].body),{expected_revision:'r',target_id:'t',expected_proposal_id:'p'});
 instance.update({...state,daily:{...state.daily,reference_quotes:{A:{sell:11}}}});resolve({ok:true,json:async()=>({status:'COMPLETE',proposal})});await pending;assert.equal(instance.elements.body.children.length,0);instance.dispose();
 let timer,gets=0,posts=0;const second=ui.mount(new Node(doc),{now:()=>clock,setTimer:f=>{timer=f;return 1;},clearTimer:()=>{},fetch:async(url,options)=>{if(options){posts++;return {ok:true,json:async()=>({status:'RUNNING',job_id:'a/b'})};}gets++;assert.equal(url,'/api/news/investment-review/job?job_id=a%2Fb');return {ok:true,json:async()=>({status:'COMPLETE',proposal})};}});
 second.update(state);await second.start();assert.equal(posts,1);assert.equal(gets,0);await timer();assert.equal(gets,1);assert.ok(second.elements.body.children.length);second.dispose();
 let ticks=new Map(),id=0,readCount=0,writeCount=0;
 const third=ui.mount(new Node(doc),{now:()=>clock,setTimer:(f,ms)=>{ticks.set(++id,{f,ms});return id;},clearTimer:i=>ticks.delete(i),fetch:async(url,options)=>{if(options){writeCount++;return {ok:true,json:async()=>({status:'COMPLETE',job_id:'job',proposal})};}readCount++;return {ok:true,json:async()=>({status:'STALE',job_id:'job',error:'REFRESH_ACCOUNT_AND_REVIEW'})};}});
 third.update(state);await third.start();const allText=n=>[n.textContent||'',...n.children.map(allText)].join(' ');assert.match(allText(third.elements.body),/历史背景，不是即时预警/);const monitor=[...ticks.values()].find(x=>x.ms===15000);assert.ok(monitor);await monitor.f();assert.equal(readCount,1);assert.equal(writeCount,1);assert.equal(third.elements.body.children.length,0);assert.match(third.elements.status.textContent,/变化/);third.dispose();
 assert.match(ui.ageText(7200),/2.0 小时/);assert.match(ui.localTime('2026-10-27T00:00:00Z'),/本地时间/);
 console.log('news investment review: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
