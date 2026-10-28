const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
for(const name of ['news_investment_review.js','strategy_daily_mount.js']){
 const actual=require.resolve('../web/'+name),candidate=path.resolve(process.env.NEWS_CASH_RETRIGGER_STAGE||'web',name);
 const loaded=new Module(actual,module);loaded.filename=actual;loaded.paths=module.paths;
 require.cache[actual]=loaded;loaded._compile(fs.readFileSync(candidate,'utf8'),actual);loaded.loaded=true;
}
const assert=require('node:assert/strict');
const ui=require('../web/strategy_daily_controller.js');
const {mount}=require('../web/strategy_daily_mount.js');
const now=Date.parse('2026-10-27T17:00:00Z'),pid='a'.repeat(64);
const account={revision:'r',cash_confirmation_valid:true,available_cash:'100',holdings:[{security_id:'S',ticker:'S',quantity:1}]};
const target={target_id:'t',proposal_id:pid,server_month:'2026-10',target_month:'2026-10',proposal_targets:[{security_id:'S',ticker:'S',quantity:2}]};
const daily=(price='10')=>({status:'READY',account_revision:'r',target_id:'t',proposal_id:pid,policy_id:'SAVED_FRONTIER_CAP50_EXIT20_V1',risk_monthly_targets:{S:2},risk_valid_from:'2026-10-27T16:00:00Z',risk_valid_until:'2026-10-27T18:00:00Z',effective_target_quantities:{S:2},daily_gate:{rows:[{security_id:'S',action:'BUY',effective_target:2}]},reference_quotes:{S:{buy:price,reference_valid_until:'2026-10-27T17:05:00Z'}},new_orders:[{security_id:'S',side:'BUY',quantity:1,limit_price:price,reference_valid_until:'2026-10-27T17:05:00Z'}]});
const proposal=()=>({review_id:'review',status:'REVIEW_PROPOSAL_ONLY',executable:false,orders_created:false,review_valid_until:'2026-10-27T17:04:00Z',original_binding:{account_revision:'r',target_id:'t',proposal_id:pid},original_preview:daily('11'),rows:[{security_id:'S',action:'EXIT',reason:'synthetic',reviewed:true,original_target_quantity:2,proposed_target_quantity:0}]});
const deps=()=>({now:()=>now,loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),previewDaily:async()=>daily(),saveCash:async()=>account,generateTarget:async()=>target});
class Node{constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}appendChild(n){n.parentNode=this;this.children.push(n);}replaceChildren(...ns){this.children=[];ns.forEach(n=>this.appendChild(n));}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(x=>x!==f);}}
const doc=new Node('document',null);doc.createElement=t=>new Node(t,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const flat=n=>[n,...n.children.flatMap(flat)];

const settle=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};

(async()=>{
 for(const change of [false,true])for(const runningJob of [false,true]){
  let revision='r',cash='100',posts=0,writes=0,activePosts=0,maxConcurrent=0;
  const responses=[],posted=[],timers=new Map();let timerId=0;let oldTerminal=null,eventOffer=false,eventJobGets=0;
  const liveAccount=()=>({...structuredClone(account),revision,available_cash:cash});
  const freshDaily=()=>({...daily(),account_revision:revision});
  const freshProposal=()=>({...proposal(),review_id:'latest-'+revision,original_binding:{...proposal().original_binding,account_revision:revision},original_preview:{...daily('11'),account_revision:revision}});
  const host=new Node('div',doc);
  const instance=mount(host,{...deps(),loadAccount:async()=>liveAccount(),previewDaily:async()=>freshDaily(),
   setTimer:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;},clearTimer:id=>timers.delete(id),
   saveCash:async request=>{writes++;cash=request.amount;if(change)revision='r'+writes;return liveAccount();},
   newsReviewFetch:async(url,options)=>{
    if(!options){if(url.includes('event-job'))eventJobGets++;return {ok:true,json:async()=>url.includes('/job?')?oldTerminal:({enabled:eventOffer,status:'REVIEW_COMPLETE',job_id:'event-job'})};}
    posts++;posted.push(JSON.parse(options.body));activePosts++;maxConcurrent=Math.max(maxConcurrent,activePosts);
    return new Promise(resolve=>responses.push(value=>{activePosts--;resolve({ok:true,json:async()=>value});}));
   }});
  await instance.ready;
  const submit=async amount=>{instance.elements.input.value=amount;instance.elements.form.listeners.submit[0]({preventDefault(){}});await instance.whenIdle();await settle();};
  await submit('100');assert.equal(posts,1);
  const old=freshProposal();old.review_id='old';
  if(runningJob){responses.shift()({status:'RUNNING',job_id:'oldjob'});await settle();}
  await submit(change?'120':'100');await submit(change?'130':'100');
  assert.equal(posts,1,'cash clicks coalesce while old POST is unresolved');assert.equal(writes,3);
  eventOffer=true;const eventPoll=[...timers.entries()].find(([,v])=>v.ms===15000);assert.ok(eventPoll);timers.delete(eventPoll[0]);await eventPoll[1].fn();assert.equal(eventJobGets,0,'event result cannot race queued cash intent');
  if(runningJob){oldTerminal={status:'COMPLETE',proposal:old};const polling=[...timers.entries()].find(([,v])=>v.ms===2000);assert.ok(polling,'cash invalidation preserves transport polling');timers.delete(polling[0]);void polling[1].fn();}
  else responses.shift()({status:'COMPLETE',proposal:old});await settle();
  assert.equal(posts,2,'one replacement for latest successful cash refresh');
  assert.equal(instance.getState().daily.new_orders[0].limit_price,'10','old result never adopted');
  assert.equal(posted[1].expected_revision,revision);
  responses.shift()({status:'COMPLETE',proposal:freshProposal()});await settle();
  assert.equal(instance.getState().daily.new_orders[0].limit_price,'11','latest valid AI original preview adopted');
  assert.equal(posts,2);assert.equal(writes,3,'AI handoff never writes cash');assert.equal(maxConcurrent,1);
  instance.dispose();
 }
 // Server may report another old RUNNING job even when this page has no flight.
 // Wait for its terminal state, then make just one new attempt. Quota denial is visible.
 let posts=0,polls=0,writes=0;const timers=new Map();let tid=0;
 const host=new Node('div',doc);
 const instance=mount(host,{...deps(),setTimer:(fn,ms)=>{timers.set(++tid,{fn,ms});return tid;},clearTimer:id=>timers.delete(id),
  saveCash:async()=>{writes++;return account;},newsReviewFetch:async(url,options)=>{
   if(options){posts++;return posts===1?{ok:false,status:409,json:async()=>({status:'RUNNING',job_id:'older',error:'ANALYSIS_ALREADY_RUNNING'})}:{ok:false,status:429,json:async()=>({status:'FAILED',error:'DAILY_REVIEW_BUDGET_EXHAUSTED'})};}
   if(url.includes('/job?')){polls++;return {ok:true,json:async()=>({status:'FAILED',error:'STALE_ACCOUNT_OR_TARGET'})};}
   return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};
  }});
 await instance.ready;instance.elements.input.value='100';instance.elements.form.listeners.submit[0]({preventDefault(){}});await instance.whenIdle();await settle();
 assert.equal(posts,1);
 const jobTimer=[...timers.entries()].find(([,v])=>v.ms===2000);assert.ok(jobTimer);timers.delete(jobTimer[0]);await jobTimer[1].fn();await settle();
 assert.equal(posts,2);assert.equal(polls,1);assert.equal(writes,1);
 assert.ok(flat(host).some(n=>String(n.textContent).includes('本日复核次数已达上限')),'budget failure is visible');
 instance.dispose();
 // Time can advance without update()/key change. An expired response must
 // terminate busy state; refreshing quotes is server work, never extending TTL.
 {
  const news=require('../web/news_investment_review.js');let clock=now,posts=0;const pending=[];
  const host=new Node('div',doc),n=news.mount(host,{now:()=>clock,setTimer:()=>1,clearTimer:()=>{},fetch:async(url,options)=>{
   if(!options)return {ok:true,json:async()=>({enabled:false})};posts++;return new Promise(resolve=>pending.push(value=>resolve({ok:true,json:async()=>value})));
  }});
  n.update({account,target,daily:daily()});void n.start();await settle();
  n.update({account,target,daily:daily('12')});void n.start();await settle();clock+=10*60*1000;
  pending.shift()({status:'FAILED'});await settle();assert.equal(posts,2);
  pending.shift()({status:'COMPLETE',proposal:proposal()});await settle();
  assert.equal(n.isBusy(),false);assert.match(n.elements.status.textContent,/失效/);n.dispose();
 }
 console.log('PASS cash refresh handoff: same/changed revision, latest intent coalescing, stale rejection, no overlapping POST, no extra cash writes, 409 wait and visible budget denial');
})().catch(e=>{console.error(e);process.exitCode=1;});

