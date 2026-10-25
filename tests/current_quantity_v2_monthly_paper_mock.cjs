const assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {create}=require('../web/current_quantity_v2_paper.js');
const f=JSON.parse(execFileSync('python',['-X','utf8','tests/current_quantity_v2_monthly_ui_fixture.py'],{cwd:require('node:path').join(__dirname,'..'),encoding:'utf8'}));
function memory(){const m=new Map();return {getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k),m};}
function harness(storage=memory()){
 let now=Date.parse(f.now),n=0;const calls=[],queue=[],timers=new Map();
 const details={open:true,style:{},addEventListener(){},removeEventListener(){}},body={innerHTML:'',querySelector(){return null;},querySelectorAll(){return [];}};
 const fetcher=(url,options)=>{calls.push({url,options});return new Promise(resolve=>queue.push(resolve));};
 const c=create(details,body,fetcher,()=>`op-${++n}`,{now:()=>now,set:(cb)=>{timers.set(++n,cb);return n;},clear:id=>timers.delete(id)},storage);
 return {c,body,calls,storage,setTime:v=>now=v,respond:(value,ok=true)=>queue.shift()({ok,json:async()=>structuredClone(value)})};
}
async function restored(data=f){const store=memory(),a=data.original;store.setItem('quantity-v2-paper-account-v1',JSON.stringify({account_id:a.account_id,decision_id:a.capital_decision_id,research_id:a.research_id,target_scope:a.target_scope,execution_target_id:a.execution_target_id,initial_capital_decision_id:a.initial_capital_decision_id,initial_research_id:a.initial_research_id,target_month:a.target_month}));const h=harness(store);h.setTime(Date.parse(data.now));h.c.setResearch(data.research);let p=h.c.restore();h.respond(a);await p;return h;}
async function selected(h,data=f){let p=h.c.monthlyCurrent();h.respond(data.selected);await p;assert.match(h.body.innerHTML,/研究已登记/);}
(async()=>{
 let h=await restored();assert.equal(h.calls.length,1);let p=h.c.monthlyCurrent();assert.match(h.calls.at(-1).url,/monthly\/research\?account_id=/);h.respond(f.current);await p;
 p=h.c.monthlyGenerate();assert.deepEqual(JSON.parse(h.calls.at(-1).options.body),{account_id:f.original.account_id,expected_revision:f.original.revision,retry_failed:false});h.respond({},false);await p;const count=h.calls.length;h.c.monthlyGenerate();assert.equal(h.calls.length,count);assert.match(h.body.innerHTML,/生成结果未确认/);
 await selected(h);p=h.c.monthlyPreview();h.respond(f.proposal);await p;assert.match(h.body.innerHTML,/data-accept/);assert.match(h.body.innerHTML,/新月目标草案/);
 p=h.c.accept();const originalBody=h.calls.at(-1).options.body;assert.match(h.calls.at(-1).url,/monthly\/accept$/);assert.equal(JSON.parse(originalBody).expected_revision,f.original.revision);h.respond({},false);await p;h.c.invalidate();assert.ok(h.storage.getItem('quantity-v2-paper-pending-v1'));
 let resumed=harness(h.storage);p=resumed.c.retry();assert.equal(resumed.calls.at(-1).options.body,originalBody);resumed.respond(f.accepted);await p;assert.equal(resumed.storage.getItem('quantity-v2-paper-pending-v1'),null);
 resumed.c.setResearch(f.research);p=resumed.c.restore();resumed.respond(f.closed);await p;p=resumed.c.continuation();assert.match(resumed.calls.at(-1).url,/continuation\/preview$/);resumed.respond(f.daily);await p;assert.match(resumed.body.innerHTML,/data-accept/);p=resumed.c.accept();assert.equal(JSON.parse(resumed.storage.getItem('quantity-v2-paper-pending-v1')).decision_id,f.daily.capital_decision_id);resumed.respond(f.daily_accepted);await p;
 // An original successful event retry can return the latest monthly active identity.
 const store=memory(),old=f.original;store.setItem('quantity-v2-paper-pending-v1',JSON.stringify({url:'/api/current_portfolio_research/paper_v2/event',account_id:old.account_id,decision_id:old.capital_decision_id,research_id:old.research_id,target_scope:old.target_scope,execution_target_id:old.execution_target_id,body:JSON.stringify({account_id:old.account_id,event:{type:'EXPIRE',event_id:'old',order_id:'old-order',expected_revision:'old'}})}));h=harness(store);p=h.c.retry();h.respond(f.accepted);await p;assert.equal(store.getItem('quantity-v2-paper-pending-v1'),null);
 // Scope, original lineage, execution identity and nondecreasing month remain strict.
 for(const change of [a=>a.initial_capital_decision_id='c'.repeat(64),a=>a.execution_target_id='bad',a=>a.target_month='2026-09']){h=await restored();const bad=structuredClone(f.accepted);change(bad);p=h.c.restore();h.respond(bad);await p;assert.match(h.body.innerHTML,/读取不可用/);const n=h.calls.length;h.c.record('EXPIRE','old',{});assert.equal(h.calls.length,n);}
 for(const change of [p=>p.prior_revision='wrong',p=>p.capital_decision_id='c'.repeat(64),p=>p.frozen_dollar_allocations_exact.B='1',p=>p.target_quantities.B++,p=>p.unit_review.coverage_complete=true,p=>p.unit_review.policy='BOUNDED_PUBLIC_KNOWN_ACTIONS_V1',p=>p.orders[0].limit_price='999999']){h=await restored();await selected(h);let bad=structuredClone(f.proposal);change(bad);p=h.c.monthlyPreview();h.respond(bad);await p;assert.doesNotMatch(h.body.innerHTML,/data-accept/);}
 h=await restored();p=h.c.monthlyCurrent();h.c.invalidate();h.respond(f.selected);await p;assert.doesNotMatch(h.body.innerHTML,/研究已登记/);
 h=await restored();p=h.c.monthlyCurrent();h.respond({...f.current,status:'PENDING',worker_liveness:'UNKNOWN'});await p;const n=h.calls.length;h.c.monthlyGenerate();assert.equal(h.calls.length,n);assert.match(h.body.innerHTML,/运行情况未知/);
 h=await restored();p=h.c.monthlyCurrent();h.respond({...f.current,status:'FAILED',reason:'MONTHLY_RESEARCH_FAILED'});await p;p=h.c.monthlyGenerate(true);assert.equal(JSON.parse(h.calls.at(-1).options.body).retry_failed,true);h.respond(f.selected);await p;
 h=await restored();await selected(h);p=h.c.monthlyPreview();h.respond(f.proposal);await p;h.setTime(Date.parse(f.proposal.reference_valid_until));const before=h.calls.length;h.c.accept();assert.equal(h.calls.length,before);assert.doesNotMatch(h.body.innerHTML,/data-accept/);
 // Actual pure monthly all-cash acceptance has no quote deadline but advances the month.
 h=await restored(f.allcash);await selected(h,f.allcash);p=h.c.monthlyPreview();h.respond(f.allcash.proposal);await p;assert.equal(f.allcash.proposal.reference_valid_until,null);assert.match(h.body.innerHTML,/采纳本月模拟目标/);p=h.c.accept();assert.match(h.calls.at(-1).url,/monthly\/accept$/);h.respond(f.allcash.accepted);await p;assert.equal(h.storage.getItem('quantity-v2-paper-pending-v1'),null);
 // Restored account is independent of a different main-card budget/decision.
 h=await restored();const changed={...f.research,decision_id:'d'.repeat(64),research_id:'d'.repeat(24),available_cash_exact:'999'};h.c.setResearch(changed);p=h.c.restore();h.respond(f.closed);await p;p=h.c.monthlyCurrent();assert.match(h.calls.at(-1).url,/monthly\/research/);h.respond({...f.current,status:'UNAVAILABLE',reason:'MONTHLY_CONFIGURATION_REQUIRED'});await p;p=h.c.continuation();assert.match(h.calls.at(-1).url,/continuation\/preview$/);h.respond(f.daily);await p;assert.match(h.body.innerHTML,/data-accept/);p=h.c.accept();h.respond(f.daily_accepted);await p;const o=f.daily_accepted.orders.find(o=>!o.closed);p=h.c.record('CANCEL',o.order_id,{cancelled_at:f.now});assert.match(h.calls.at(-1).url,/event$/);assert.equal(JSON.parse(h.calls.at(-1).options.body).account_id,f.original.account_id);h.respond({mutation_outcome:'NOT_APPLIED'},false);await p;
 // Optional saved bridge fixture is mandatory when explicitly supplied; never synthesize a monthly response.
 if(process.argv[2]){
  const actual=JSON.parse(require('node:fs').readFileSync(process.argv[2],'utf8'));
  const proposed=actual.proposal,ids=Object.keys(proposed.execution_references),buy=proposed.orders.find(o=>o.side==='BUY'),sell=proposed.orders.find(o=>o.side==='SELL');
  assert.ok(ids.length&&buy,'actual fixture must contain a monthly pullback BUY');
  assert.ok(ids.every(sid=>proposed.execution_references[sid].pullback?.execution_policy));
  h=await restored(actual);await selected(h,actual);p=h.c.monthlyPreview();h.respond(proposed);await p;
  assert.match(h.body.innerHTML,/data-accept/);assert.match(h.body.innerHTML,/新月目标草案/);
  if(sell){assert.ok(Number(sell.limit_price.split('/')[0])>0);assert.match(h.body.innerHTML,/卖出建议 1 项/);assert.match(h.body.innerHTML,/data-sell-reason/);assert.match(h.body.innerHTML,/报价时间（北京时间）/);if(buy)assert.match(h.body.innerHTML,/买入建议 1 项/);}
  const targetSid=buy.security_id;
  for(const mutate of [
   value=>value.orders.find(o=>o.side==='BUY').limit_price='999999',
   value=>value.execution_references[targetSid].pullback.binding.security_id='WRONG',
   value=>value.execution_references[targetSid].pullback.execution_policy.rebound_fraction='1/4',
   value=>value.execution_references[targetSid].pullback.reference_valid_until=actual.now,
   value=>value.execution_references[targetSid].pullback.prior_cap={...structuredClone(value.execution_references[targetSid].pullback.cap_declaration),limit_price:'1'},
   value=>{delete value.execution_references[targetSid].pullback;},
  ]){
   h=await restored(actual);await selected(h,actual);const bad=structuredClone(proposed);mutate(bad);p=h.c.monthlyPreview();h.respond(bad);await p;assert.doesNotMatch(h.body.innerHTML,/data-accept/);
  }
  if(sell){h=await restored(actual);await selected(h,actual);const bad=structuredClone(proposed);bad.orders.find(o=>o.side==='SELL').limit_price=bad.execution_references[sell.security_id].pullback.limit_price;p=h.c.monthlyPreview();h.respond(bad);await p;assert.doesNotMatch(h.body.innerHTML,/data-accept/,'SELL must use ceil(last), not pullback BUY price');}
  console.log('PASS actual monthly pullback bridge fixture: exact BUY allocation, unchanged SELL pricing, policy/identity/prior-cap/time tamper rejection.');
 }
 console.log('PASS monthly UI: real tiny registry/raw HTTP fixture; stable genesis and active targets; manual research/preview/accept; exact retry; scope, deadlines, cash changes and failed recovery.');
})().catch(e=>{console.error(e);process.exitCode=1;});
