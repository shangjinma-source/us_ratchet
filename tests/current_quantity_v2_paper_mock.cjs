const assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {create}=require('../web/current_quantity_v2_paper.js');
const fixture=JSON.parse(execFileSync('python',['-X','utf8','-c',`
import sys,json,tempfile
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,'tests')
from test_current_quantity_v2_difference_cash_service import fixture
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_service import compact
from data.current_quantity_v2_paper_chain import record_chain_event
from datetime import datetime
s,i,p,a,c=fixture();decision=json.loads(p['files'][p['documents']['capital_decision']]);v=project_capital_decision_v2(decision)
v.update(decision_id=i,research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH')
preview=s.preview(i)
with tempfile.TemporaryDirectory() as folder:
 paper=QuantityV2PaperService(store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3'),initial_resolver=s.initial_resolver,clock=lambda:c[0])
 accepted=paper.accept(account_id=a['account_id'],proposal_id=preview['proposal_id'],operation_id='op1')
 o=accepted['orders'][0];c[0]+=timedelta(seconds=1)
 fields=dict(quantity=1,price='8',fees='0',executed_at=c[0].isoformat())
 filled=paper.event(account_id=a['account_id'],event=dict(event_id='fill1',type='FILL',order_id=o['order_id'],expected_revision=accepted['revision'],**fields))
 close=datetime.fromisoformat(o['session_close'])+timedelta(seconds=1)
 expired=compact(record_chain_event(paper.store.read(a['account_id']),dict(event_id='expire1',type='EXPIRE',order_id=o['order_id'],expected_revision=filled['revision'],recorded_at=close.isoformat()),now=close))
 c[0]+=timedelta(seconds=1)
 cancelled=paper.event(account_id=a['account_id'],event=dict(event_id='cancel1',type='CANCEL',order_id=o['order_id'],expected_revision=filled['revision'],cancelled_at=c[0].isoformat()))
 initial=dict(research=v,preview=preview,accepted=accepted,filled=filled,cancelled=cancelled,expired=expired,fields=fields)
from test_current_quantity_v2_continuation_service import fixture as continuation_fixture
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_paper import create_router,PREFIX
with tempfile.TemporaryDirectory() as folder:
 paper,bridge,package,c,closed=continuation_fixture(folder)
 closed=paper.account(closed['account_id'])
 app=FastAPI();app.include_router(create_router(service=paper))
 with TestClient(app) as client:
  cp=client.post(PREFIX+'/continuation/preview',json=dict(account_id=closed['account_id'],expected_revision=closed['revision']))
  assert cp.status_code==200,cp.text
  now=c[0].isoformat();proposal=cp.json();c[0]+=timedelta(seconds=1)
  ca=client.post(PREFIX+'/continuation/accept',json=dict(account_id=closed['account_id'],proposal_id=proposal['proposal_id'],operation_id='node-continuation',expected_revision=closed['revision']))
  assert ca.status_code==200,ca.text
  initial.update(continuation=dict(closed=closed,proposal=proposal,accepted=ca.json(),now=now))
import test_current_quantity_v2_current_cash_plan as cash_base
from test_current_quantity_v2_current_cash_service import fixture as cash_fixture,app_for
from fractions import Fraction
cash_base.CurrentCashTests.setUpClass()
try:
 args=cash_base.CurrentCashTests.args;decision=args['capital_decision'];v=project_capital_decision_v2(decision)
 v.update(decision_id=decision['decision_id'],research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH',frozen_dollar_allocations_exact={sid:str(q*Fraction(decision['binding']['search_arguments']['prices'][sid])) for sid,q in decision['target_quantities'].items() if q>0})
 with tempfile.TemporaryDirectory() as folder:
  source,paper,supplied,account,c=cash_fixture(folder,args)
  with TestClient(app_for(source,paper)) as client:
   cp=client.post('/api/current_portfolio_research/difference',json={'decision_id':decision['decision_id']});assert cp.status_code==200,cp.text
   preview=cp.json();now=c[0].isoformat();c[0]+=timedelta(seconds=1)
   ca=client.post(PREFIX+'/accept',json=dict(account_id=account['account_id'],proposal_id=preview['proposal_id'],operation_id='cash-node'));assert ca.status_code==200,ca.text
   accepted=ca.json();c[0]+=timedelta(seconds=1);o=accepted['orders'][0]
   fields=dict(quantity=1,price='9',fees='1/5',executed_at=c[0].isoformat())
   filled=client.post(PREFIX+'/event',json=dict(account_id=account['account_id'],event=dict(event_id='cash-fill',type='FILL',order_id=o['order_id'],expected_revision=accepted['revision'],**fields)));assert filled.status_code==200,filled.text
   initial['current_cash']=dict(research=v,preview=preview,accepted=accepted,filled=filled.json(),fields=fields,now=now)
 from copy import deepcopy
 keep_args=deepcopy(args);ep=keep_args['execution_package'];files=ep['files'];pins=ep['source_hashes'];docs=ep['documents'];units=json.loads(files[docs['current_unit_reviews']])
 from hashlib import sha256
 def repath(path,value):
  files[path]=json.dumps(value,sort_keys=True).encode();pins[path]=sha256(files[path]).hexdigest()
 for sid,rp in docs['quote_receipts'].items():
  rr=json.loads(files[rp]);rawp=rr['raw_path'];files[rawp]=cash_base.raw(rr['ticker'],1000);pins[rawp]=sha256(files[rawp]).hexdigest();rr['raw_sha256']=pins[rawp];repath(rp,rr);units[sid]['reference_source_hashes']={rawp:pins[rawp],rp:pins[rp]}
 repath(docs['current_unit_reviews'],units)
 with tempfile.TemporaryDirectory() as folder:
  source,paper,_,_,_=cash_fixture(folder,keep_args)
  with TestClient(app_for(source,paper)) as client:
   kept=client.post('/api/current_portfolio_research/difference',json={'decision_id':decision['decision_id']});assert kept.status_code==200,kept.text
   initial['current_cash']['keep']=kept.json();assert initial['current_cash']['keep']['action']=='KEEP_CASH'
 from test_current_quantity_v2_current_cash_continuation_http import fixture as cc_fixture
 with tempfile.TemporaryDirectory() as folder:
  paper,bridge,package,c,closed=cc_fixture(folder,args)
  closed=paper.account(closed['account_id'])
  app=FastAPI();app.include_router(create_router(service=paper))
  with TestClient(app) as client:
   cp=client.post(PREFIX+'/continuation/preview',json=dict(account_id=closed['account_id'],expected_revision=closed['revision']));assert cp.status_code==200,cp.text
   initial['current_cash']['continuation']=dict(closed=closed,proposal=cp.json(),now=c[0].isoformat())
finally:cash_base.CurrentCashTests.tearDownClass()
print(json.dumps(initial))
`],{cwd:require('node:path').join(__dirname,'..'),encoding:'utf8'}));
const memory=()=>{const m=new Map();return {getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k),m};};
function harness(storage=memory()){
 let now=Date.parse('2026-10-15T12:00:32-04:00'),n=0;const calls=[],wait=[],timers=new Map();
 const details={open:true,style:{},addEventListener(k,f){this[k]=f;}},body={innerHTML:'',querySelector(){return null;},querySelectorAll(){return [];}};
 const events={},registrations=[];const document={hidden:false,addEventListener(k,f){events[k]=f;registrations.push(k);}};
 const oldDocument=globalThis.document,oldListener=globalThis.addEventListener;globalThis.document=document;globalThis.addEventListener=(k,f)=>{events[k]=f;registrations.push(k);};
 const c=create(details,body,(url,options)=>{calls.push({url,options});return new Promise(r=>wait.push(r));},()=>`uuid-${++n}`,{now:()=>now,set:(f,delay)=>{const id=++n;timers.set(id,{f,at:now+delay});return id;},clear:n=>timers.delete(n)},storage);
 globalThis.document=oldDocument;globalThis.addEventListener=oldListener;
 return {c,body,details,calls,storage,timers,events,document,registrations,advanceWithoutTimers:t=>{now=t;},respond:(data,ok=true)=>wait.shift()({ok,json:async()=>data}),setTime:t=>{now=t;for(const [k,v]of [...timers])if(v.at<=now){timers.delete(k);v.f();}}};
}
const tick=()=>new Promise(r=>setImmediate(r));
async function preview(h){h.c.setResearch(fixture.research);const p=h.c.preview();h.respond(fixture.preview);await p;assert.match(h.body.innerHTML,/AAA/);assert.match(h.body.innerHTML,/8.00/);}
(async()=>{
 if(process.argv[4]){
  const saved=JSON.parse(require('node:fs').readFileSync(process.argv[4],'utf8'));
  for(const mode of ['monthly','daily']){
   const a=mode==='monthly'?saved.original:saved.closed,storage=memory();
   storage.setItem('quantity-v2-paper-account-v1',JSON.stringify({account_id:a.account_id,decision_id:a.capital_decision_id,research_id:a.research_id,target_scope:a.target_scope,execution_target_id:a.execution_target_id,target_month:a.target_month,initial_capital_decision_id:a.initial_capital_decision_id,initial_research_id:a.initial_research_id}));
   const actual=harness(storage);actual.setTime(Date.parse(saved.now));actual.c.setResearch(saved.research);let reading=actual.c.restore();actual.respond(a);await reading;
   if(mode==='monthly'){reading=actual.c.monthlyCurrent();actual.respond(saved.current);await reading;reading=actual.c.monthlyPreview();actual.respond(saved.proposal);await reading;}
   else{reading=actual.c.continuation();actual.respond(saved.daily);await reading;}
   const sellRow=actual.body.innerHTML.split('<tr>').find(row=>row.includes('data-sell-reason'));assert.ok(sellRow,'actual '+mode+' SELL row');
   assert.match(sellRow,/持有 2 股 → 目标 0 股 → 减持 2 股/);assert.match(sellRow,/近现价卖出参考 · 非已验证卖点/);assert.doesNotMatch(sellRow,/试运行回落价/);
   assert.match(sellRow,mode==='monthly'?/月度选股后不再持有/:/继续完成本月减仓目标/);assert.equal(actual.calls.some(call=>call.url.endsWith('/accept')),false);
  }
  console.log('PASS actual monthly/continuation SELL reason and held-target-delta; entry label absent on SELL; no accept');
 }
 if(process.argv[2]){
  const saved=JSON.parse(require('node:fs').readFileSync(process.argv[2],'utf8'));
  assert.equal(saved.historical_fixture_only,true);assert.equal(saved.network_calls,0);assert.equal(saved.calculate_calls,0);
  const actual=harness();actual.setTime(Date.parse(saved.clock));actual.c.setResearch(saved.research);
  const reading=actual.c.preview();actual.respond(saved.preview);await reading;
  assert.match(actual.body.innerHTML,/试运行回落价/);assert.match(actual.body.innerHTML,/\$1317.12/);assert.match(actual.body.innerHTML,/\$1276.07/);assert.match(actual.body.innerHTML,/SNDK/);assert.match(actual.body.innerHTML,/data-accept/);
  assert.equal(actual.calls.length,1);assert.deepEqual(JSON.parse(actual.calls[0].options.body),{decision_id:saved.research.decision_id});
  actual.setTime(Date.parse(saved.preview.reference_valid_until));assert.doesNotMatch(actual.body.innerHTML,/data-accept|<strong>\$1317.12/);assert.equal(actual.calls.length,1);
  console.log('PASS saved actual pullback pipeline response: SNDK 1317.12 / observed low 1276.07; no accept or network; expiry removes draft');
 }
 if(process.argv[3]){
  const saved=JSON.parse(require('node:fs').readFileSync(process.argv[3],'utf8')),a=saved.account,storage=memory();
  storage.setItem('quantity-v2-paper-account-v1',JSON.stringify({account_id:a.account_id,decision_id:a.capital_decision_id,research_id:a.research_id,target_scope:a.target_scope,execution_target_id:a.execution_target_id,target_month:a.target_month}));
  const actual=harness(storage);actual.setTime(Date.parse(saved.clock_now));actual.c.setResearch(saved.research);
  let reading=actual.c.restore();actual.respond(a);await reading;
  reading=actual.c.continuation();actual.respond(saved.response);await reading;
  assert.match(actual.body.innerHTML,/试运行回落价/);assert.match(actual.body.innerHTML,/\$9.00/);assert.match(actual.body.innerHTML,/data-accept/);assert.doesNotMatch(actual.body.innerHTML,/旧参考规则/);
  for(const modify of [r=>r.pullback.limit_price='9.01',r=>r.pullback.execution_policy.minimum_discount='1/5',r=>r.pullback.prior_cap.binding.policy_id='f'.repeat(64),r=>r.captured_at='2099-01-01T00:00:00Z']){
   const bad=structuredClone(saved.response);modify(Object.values(bad.execution_references)[0]);reading=actual.c.continuation();actual.respond(bad);await reading;assert.match(actual.body.innerHTML,/读取不可用/);assert.doesNotMatch(actual.body.innerHTML,/data-accept/);
  }
  assert.equal(actual.calls.every(call=>!call.url.endsWith('/accept')),true);console.log('PASS actual continuation bridge response: inherited pullback cap 9.00, tampering rejected, no accept or network');
 }
 for(const [reason,expected] of [['RESEARCH_SOURCE_WITHDRAWN',/历史价格口径待核的 TRI.*暂停新建议.*重复刷新不能解决/],['RESEARCH_SNAPSHOT_EXPIRED',/组合预览已失效.*读取当前金额候选.*再生成草案/],['MONTH_MANDATE_REQUIRED',/缺少本月执行授权/],['RESELECT_REQUIRED',/需要重新选股/],['EXECUTION_MONTH_NOT_ACTIVE',/不在已授权的执行月份/],['OUTSIDE_REGULAR_SESSION',/不在美股正常交易时段/],['LAST_QUOTE_FUTURE',/行情时间领先电脑时钟.*Windows.*同步/],['LAST_QUOTE_STALE',/成交报价已过期/],['NO_COMPLETED_VALID_MINUTE',/尚无可用的完整一分钟/],['SOURCE_UNAVAILABLE',/行情或来源依据暂不可用/],['private/path:secret',/读取不可用/],['constructor',/读取不可用/],['__proto__',/读取不可用/],['toString',/读取不可用/]]){
  const x=harness();await preview(x);const pendingRead=x.c.preview();x.respond({status:'UNAVAILABLE',reason},false);await pendingRead;
  assert.equal(x.calls.length,2,'controlled failure must not automatically reload research or retry');assert.match(x.body.innerHTML,expected);if(!['RESEARCH_SOURCE_WITHDRAWN','RESEARCH_SNAPSHOT_EXPIRED','RESELECT_REQUIRED'].includes(reason))assert.match(x.body.innerHTML,/上次建议保留待刷新/);assert.doesNotMatch(x.body.innerHTML,/输入可动用现金后/);assert.doesNotMatch(x.body.innerHTML,/data-accept|private\/path|secret|native code|function Object/);
 }
 // Recreating on the same element or explicitly destroying removes lifecycle listeners.
 const lifecycleListeners=new Map(),docListeners=new Map(),detailListeners=new Map();
 const oldDoc=globalThis.document,oldAdd=globalThis.addEventListener,oldRemove=globalThis.removeEventListener;
 const add=(map,k,f)=>{if(!map.has(k))map.set(k,new Set());map.get(k).add(f);},remove=(map,k,f)=>map.get(k)?.delete(f);
 globalThis.document={hidden:false,addEventListener:(k,f)=>add(docListeners,k,f),removeEventListener:(k,f)=>remove(docListeners,k,f)};
 globalThis.addEventListener=(k,f)=>add(lifecycleListeners,k,f);globalThis.removeEventListener=(k,f)=>remove(lifecycleListeners,k,f);
 try{const d={open:true,style:{},addEventListener:(k,f)=>add(detailListeners,k,f),removeEventListener:(k,f)=>remove(detailListeners,k,f)},b={innerHTML:'',querySelector(){return null;},querySelectorAll(){return [];}};
  const make=()=>create(d,b,()=>{throw Error('unexpected HTTP');},()=>'',undefined,memory());
  const first=make(),second=make();assert.equal(lifecycleListeners.get('focus').size,1);assert.equal(docListeners.get('visibilitychange').size,1);assert.equal(detailListeners.get('toggle').size,1);
  first.destroy();assert.equal(lifecycleListeners.get('focus').size,1);second.destroy();assert.equal(lifecycleListeners.get('focus').size,0);assert.equal(docListeners.get('visibilitychange').size,0);assert.equal(detailListeners.get('toggle').size,0);
 }finally{globalThis.document=oldDoc;globalThis.addEventListener=oldAdd;globalThis.removeEventListener=oldRemove;}
 // Browser background timers may be suspended: every resume path removes an expired draft.
 for(const event of ['focus','pageshow','visibilitychange']){
  const resumed=harness();await preview(resumed);resumed.advanceWithoutTimers(Date.parse(fixture.preview.reference_valid_until));
  assert.match(resumed.body.innerHTML,/data-accept/); // Deliberately never run the due timer.
  if(event==='visibilitychange'){resumed.document.hidden=true;resumed.events[event]();assert.match(resumed.body.innerHTML,/data-accept/);resumed.document.hidden=false;}
  resumed.events[event]();assert.match(resumed.body.innerHTML,/<strong>\$8.00<\/strong>/);assert.match(resumed.body.innerHTML,/待刷新/);assert.doesNotMatch(resumed.body.innerHTML,/data-accept/);assert.equal(resumed.timers.size,0);
  resumed.events[event]();resumed.c.accept();assert.equal(resumed.calls.length,1);assert.equal(resumed.registrations.length,3);
 }
 // Expiry during an unknown mutation removes only its displayed draft, not the retry request.
 const uncertain=harness();await preview(uncertain);let operation=uncertain.c.accept();const exactRequest=uncertain.calls.at(-1).options.body;
 uncertain.respond({mutation_outcome:'UNKNOWN_RETRY_SAME_REQUEST'},false);await operation;
 const savedPending=uncertain.storage.getItem('quantity-v2-paper-pending-v1');
 uncertain.advanceWithoutTimers(Date.parse(fixture.preview.reference_valid_until)+1);uncertain.events.focus();
 assert.doesNotMatch(uncertain.body.innerHTML,/data-accept/);assert.match(uncertain.body.innerHTML,/重试原操作/);
 assert.equal(uncertain.storage.getItem('quantity-v2-paper-pending-v1'),savedPending);
 operation=uncertain.c.retry();assert.equal(uncertain.calls.at(-1).options.body,exactRequest);uncertain.respond(fixture.accepted);await operation;
 uncertain.events.pageshow();assert.match(uncertain.body.innerHTML,/DAY 未结单/);assert.match(uncertain.body.innerHTML,/限价 \$8.00/);
 // Rendering after a delayed response must also expire without waiting for any lifecycle event.
 const rendering=harness();await preview(rendering);operation=rendering.c.accept();rendering.advanceWithoutTimers(Date.parse(fixture.preview.reference_valid_until)+1);
 rendering.respond({mutation_outcome:'UNKNOWN_RETRY_SAME_REQUEST'},false);await operation;
 assert.doesNotMatch(rendering.body.innerHTML,/data-accept/);assert.match(rendering.body.innerHTML,/重试原操作/);
 let h=harness();await preview(h);assert.equal(h.calls.length,1);assert.deepEqual(JSON.parse(h.calls[0].options.body),{decision_id:fixture.research.decision_id});
 let p=h.c.accept();assert.equal(h.storage.m.size,1);const original=h.calls.at(-1).options.body;h.respond({mutation_outcome:'UNKNOWN_RETRY_SAME_REQUEST'},false);await p;
 h.c.invalidate();assert.match(h.body.innerHTML,/重试原操作/);const blocked=h.calls.length;h.c.preview();assert.equal(h.calls.length,blocked);
 const restored=harness(h.storage);assert.equal(restored.calls.length,0);p=restored.c.retry();assert.equal(restored.calls[0].options.body,original);restored.respond(fixture.accepted);await p;assert.match(restored.body.innerHTML,/100.00/);assert.equal(restored.storage.m.has('quantity-v2-paper-pending-v1'),false);
 // Reload restores account ID without a new candidate/preview, only manual read.
 const r=harness(h.storage);assert.match(r.body.innerHTML,/读取模拟跟踪/);p=r.c.restore();r.respond(fixture.accepted);await p;assert.match(r.body.innerHTML,/独立模拟账户/);assert.match(r.body.innerHTML,/模拟余额/);assert.match(r.body.innerHTML,/模拟持仓/);assert.doesNotMatch(r.body.innerHTML,/synthetic-account/);
 r.c.setResearch(fixture.research);p=r.c.restore();r.respond(fixture.accepted);await p;r.setTime(Date.parse(fixture.fields.executed_at));p=r.c.record('FILL',fixture.accepted.orders[0].order_id,fixture.fields);const fillBody=JSON.parse(r.calls.at(-1).options.body);assert.equal(fillBody.event.quantity,1);assert.equal('recorded_at' in fillBody.event,false);r.respond(fixture.filled);await p;assert.match(r.body.innerHTML,/92.00/);
 const expiry=harness(h.storage);expiry.c.setResearch(fixture.research);p=expiry.c.restore();expiry.respond(fixture.filled);await p;
 const pre=expiry.calls.length;expiry.c.record('EXPIRE',fixture.accepted.orders[0].order_id,{});assert.equal(expiry.calls.length,pre);
 expiry.setTime(Date.parse(fixture.accepted.orders[0].session_close)+1000);p=expiry.c.record('EXPIRE',fixture.accepted.orders[0].order_id,{});
 const expiryBody=expiry.calls.at(-1).options.body;assert.deepEqual(Object.keys(JSON.parse(expiryBody).event).sort(),['event_id','expected_revision','order_id','type']);
 expiry.respond({mutation_outcome:'UNKNOWN_RETRY_SAME_REQUEST'},false);await p;
 const expiryRetry=harness(h.storage);p=expiryRetry.c.retry();assert.equal(expiryRetry.calls.at(-1).options.body,expiryBody);expiryRetry.respond(fixture.expired);await p;
 assert.match(expiryRetry.body.innerHTML,/EXPIRED/);assert.equal(fixture.expired.reserved_cash,'0');assert.equal(fixture.expired.cash,'92');assert.deepEqual(fixture.expired.shares,fixture.filled.shares);
 r.setTime(Date.parse('2026-10-15T12:00:34-04:00'));p=r.c.record('CANCEL',fixture.accepted.orders[0].order_id,{cancelled_at:'2026-10-16T00:00:34+08:00'});r.respond(fixture.cancelled);await p;assert.match(r.body.innerHTML,/CANCELLED/);
 // Restored account remains independently writable; new main-card cash never changes its identity.
 const samePrefix=harness(h.storage);samePrefix.c.setResearch({...fixture.research,decision_id:fixture.research.research_id+'f'.repeat(40)});p=samePrefix.c.restore();samePrefix.respond(fixture.accepted);await p;samePrefix.setTime(Date.parse(fixture.fields.executed_at));const prefixCalls=samePrefix.calls.length;p=samePrefix.c.record('FILL',fixture.accepted.orders[0].order_id,fixture.fields);assert.equal(samePrefix.calls.length,prefixCalls+1);assert.equal(JSON.parse(samePrefix.calls.at(-1).options.body).account_id,fixture.accepted.account_id);samePrefix.respond({mutation_outcome:'NOT_APPLIED'},false);await p;assert.match(samePrefix.body.innerHTML,/独立模拟账户/);
 r.c.setResearch({...fixture.research,research_id:'a'.repeat(24),decision_id:'a'.repeat(64)});p=r.c.restore();r.respond(fixture.accepted);await p;const before=r.calls.length;p=r.c.record('FILL',fixture.accepted.orders[0].order_id,fixture.fields);assert.equal(r.calls.length,before+1);assert.equal(JSON.parse(r.calls.at(-1).options.body).account_id,fixture.accepted.account_id);r.respond({mutation_outcome:'NOT_APPLIED'},false);await p;assert.match(r.body.innerHTML,/独立模拟账户/);assert.match(r.body.innerHTML,/模拟余额/);assert.match(r.body.innerHTML,/模拟持仓/);
 // Full persisted lineage is authoritative, even if the bad response matches a new research.
 const lineage=harness(h.storage);lineage.c.setResearch({...fixture.research,research_id:'a'.repeat(24),decision_id:'a'.repeat(64)});p=lineage.c.restore();lineage.respond({...fixture.accepted,research_id:'a'.repeat(24),capital_decision_id:'a'.repeat(64)});await p;assert.match(lineage.body.innerHTML,/读取不可用/);const oldCalls=lineage.calls.length;lineage.c.record('FILL',fixture.accepted.orders[0].order_id,fixture.fields);assert.equal(lineage.calls.length,oldCalls);
 // A new, unaccepted preview must not replace the saved account's decision binding.
 p=lineage.c.preview();lineage.respond({...fixture.preview,research_id:'a'.repeat(24),decision_id:'a'.repeat(64)});await p;p=lineage.c.restore();lineage.respond(fixture.accepted);await p;assert.match(lineage.body.innerHTML,/独立模拟账户/);
 h=harness();await preview(h);h.setTime(Date.parse(fixture.preview.reference_valid_until));assert.match(h.body.innerHTML,/<strong>\$8.00<\/strong>/);assert.match(h.body.innerHTML,/待刷新/);const count=h.calls.length;h.c.accept();assert.equal(h.calls.length,count);
 h=harness();h.c.setResearch(fixture.research);p=h.c.preview();h.c.invalidate();h.respond(fixture.preview);await p;assert.doesNotMatch(h.body.innerHTML,/data-accept|<strong>\$/);
 for(const mutate of [p=>p.decision_id='a'.repeat(64),p=>p.research_id='a'.repeat(24),p=>p.remaining_cash='5',p=>p.target_scope='ACCOUNT_EQUITY_TARGET',p=>p.orders[0].security_id='OTHER']){h=harness();h.c.setResearch(fixture.research);p=h.c.preview();let bad=structuredClone(fixture.preview);mutate(bad);h.respond(bad);await p;assert.match(h.body.innerHTML,/读取不可用/);assert.doesNotMatch(h.body.innerHTML,/限价 \$8.00/);}
 h=harness();await preview(h);p=h.c.accept();h.respond({mutation_outcome:'NOT_APPLIED'},false);await p;assert.equal(h.storage.m.has('quantity-v2-paper-pending-v1'),false);assert.doesNotMatch(h.body.innerHTML,/重试原操作/);
 const broken=memory();broken.setItem=()=>{throw Error('quota');};h=harness(broken);await preview(h);const b=h.calls.length;await h.c.accept();assert.equal(h.calls.length,b);
 const poisoned=memory();poisoned.setItem('quantity-v2-paper-pending-v1',JSON.stringify({url:'https://evil',body:'{}'}));h=harness(poisoned);await h.c.retry();assert.equal(h.calls.length,0);
 // Continuation uses real Python ASGI preview/accept JSON, current 83.80 cash, fixed original target.
 const cf=fixture.continuation;
 async function continuationAccount(){const store=memory();store.setItem('quantity-v2-paper-account-v1',JSON.stringify({account_id:cf.closed.account_id,research_id:cf.closed.research_id,decision_id:cf.closed.capital_decision_id}));const x=harness(store);x.setTime(Date.parse(cf.now));x.c.setResearch(fixture.research);let q=x.c.restore();x.respond(cf.closed);await q;return x;}
 for(const capabilities of [undefined,{continuation:{configured:false,reason:'UNIT_REVIEW_SOURCE_UNAVAILABLE'}},{continuation:{configured:'true'}}]){h=await continuationAccount();p=h.c.restore();h.respond({...structuredClone(cf.closed),capabilities});await p;const before=h.calls.length;h.c.continuation();assert.equal(h.calls.length,before);assert.match(h.body.innerHTML,/暂不能续单/);}
 h=await continuationAccount();p=h.c.continuation();assert.deepEqual(JSON.parse(h.calls.at(-1).options.body),{account_id:cf.closed.account_id,expected_revision:cf.closed.revision});h.respond(cf.proposal);await p;assert.match(h.body.innerHTML,/83.80/);assert.match(h.body.innerHTML,/10 股/);
 p=h.c.accept();const continuationBody=h.calls.at(-1).options.body;assert.equal(h.calls.at(-1).url,'/api/current_portfolio_research/paper_v2/continuation/accept');assert.equal(JSON.parse(continuationBody).expected_revision,cf.closed.revision);h.respond({mutation_outcome:'UNKNOWN_RETRY_SAME_REQUEST'},false);await p;h.c.invalidate();
 const continued=harness(h.storage);assert.equal(continued.calls.length,0);p=continued.c.retry();assert.equal(continued.calls[0].options.body,continuationBody);continued.respond(cf.accepted);await p;assert.match(continued.body.innerHTML,/83.80/);assert.match(continued.body.innerHTML,/独立模拟账户/);
 for(const change of [x=>x.account_id='other',x=>x.capital_decision_id='f'.repeat(64),x=>x.prior_revision='old',x=>x.target_month='2026-11',x=>x.recorded_fees='0',x=>x.orders_created=true,x=>x.account_mutated=true,x=>x.actual_cash='100',x=>x.shares.A=3,x=>x.orders[0].quantity=100,x=>x.remaining_cash='100',x=>{x.orders=[];x.action='NO_ACTION';x.proposal_id=null;x.reserved_buy_cash='0';x.remaining_cash=x.actual_cash;},x=>{x.orders=[];x.action='WAIT_CASH';x.proposal_id=null;x.wait_cash=[];x.reserved_buy_cash='0';x.remaining_cash=x.actual_cash;}]){h=await continuationAccount();p=h.c.continuation();const bad=structuredClone(cf.proposal);change(bad);h.respond(bad);await p;assert.match(h.body.innerHTML,/读取不可用/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);assert.match(h.body.innerHTML,/83.80/);}
 // Empty WAIT_CASH remains informative, never an empty acceptance.
 h=await continuationAccount();p=h.c.continuation();const waiting={...structuredClone(cf.proposal),orders:[],proposal_id:null,action:'WAIT_CASH',reserved_buy_cash:'0',remaining_cash:cf.closed.cash,wait_cash:[{security_id:'A',remaining_deficit:48,reason:'CASH'}]};h.respond(waiting);await p;assert.match(h.body.innerHTML,/现金不足/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);
 // Synthetic empty-domain response: only equal held and targets may claim NO_ACTION.
 h=await continuationAccount();const doneAccount={...structuredClone(cf.closed),target_quantities:structuredClone(cf.closed.shares)};p=h.c.restore();h.respond(doneAccount);await p;p=h.c.continuation();h.respond({...structuredClone(waiting),action:'NO_ACTION',wait_cash:[],target_quantities:doneAccount.target_quantities});await p;assert.match(h.body.innerHTML,/已达到本月目标/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);
 // A failed/late read cannot revive an old proposal; unresolved mutation freezes all new operations.
 h=await continuationAccount();p=h.c.continuation();h.respond(cf.proposal);await p;p=h.c.accept();h.respond({},false);await p;const locked=h.calls.length;h.c.continuation();h.c.restore();h.c.preview();assert.equal(h.calls.length,locked);
 h=await continuationAccount();p=h.c.continuation();h.respond(cf.proposal);await p;h.setTime(Date.parse(cf.proposal.reference_valid_until));const nc=h.calls.length;h.c.accept();assert.equal(h.calls.length,nc);assert.doesNotMatch(h.body.innerHTML,/data-accept/);
 h=await continuationAccount();p=h.c.continuation();h.c.invalidate();h.respond(cf.proposal);await p;assert.doesNotMatch(h.body.innerHTML,/data-accept/);
 h=await continuationAccount();h.c.setResearch({...fixture.research,research_id:'f'.repeat(24),decision_id:'f'.repeat(64)});p=h.c.restore();h.respond(cf.closed);await p;const frozen=h.calls.length;p=h.c.continuation();assert.equal(h.calls.length,frozen+1);h.respond(cf.proposal);await p;assert.match(h.body.innerHTML,/data-accept/);
 // New current-cash scope uses actual tiny-worker decision + real ASGI bridge/ledger.
 const cash=fixture.current_cash;
 async function cashPreview(research=cash.research,response=cash.preview){const x=harness();x.setTime(Date.parse(cash.now));x.c.setResearch(research);const q=x.c.preview();x.respond(response);await q;return x;}
 // Compact primary advice stays separate from optional simulation management.
 const compact=harness();await preview(compact);
 assert.doesNotMatch(compact.body.innerHTML,/data-restore/,'unaccepted preview is not a saved account');
 assert.equal(compact.storage.getItem('quantity-v2-paper-account-v1'),null);
 const previewOnlyCalls=compact.calls.length;await compact.c.restore();assert.equal(compact.calls.length,previewOnlyCalls,'no restore request before account exists');
 const primary=compact.body.innerHTML.split('<details class="limit-details" data-simulation-records>')[0];
 assert.match(primary,/<th>建议限价<\/th>/);assert.match(primary,/<th>当前参考价<\/th>/);
 assert.match(primary,/<td>—<\/td>/,'legacy proposal must not invent reference timestamps or prices');
 assert.doesNotMatch(primary,/data-restore|data-accept|读取模拟跟踪/);
 assert.match(compact.body.innerHTML,/<details class="limit-details" data-simulation-records><summary>策略验证 · 模拟记录（可选）<\/summary>[\s\S]*data-accept/);
 assert.doesNotMatch(compact.body.innerHTML,/<details[^>]*data-simulation-records[^>]*\bopen\b/);
 assert.match(compact.body.innerHTML,/不代表券商成交/);assert.match(compact.body.innerHTML,/真实成交请到「操作与持仓」录入/);
 const page=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');assert.match(page,/这里记录券商实际持仓；模拟成交不会同步到此/);
 const compactRequests=compact.calls.length;compact.setTime(Date.parse(fixture.preview.reference_valid_until));
 assert.match(compact.body.innerHTML.split('<details class="limit-details" data-simulation-records>')[0],/上次建议报价已过期，待刷新；旧报价不可采纳，不会自动撤销已记录的当日挂单/);
 assert.doesNotMatch(compact.body.innerHTML,/data-accept/);
 assert.equal(compact.calls.length,compactRequests,'expiry never refreshes quotes automatically');
 h=await cashPreview();assert.match(h.body.innerHTML,/本次报价校验有效至/);assert.match(h.body.innerHTML,/120 秒数据新鲜窗口/);assert.match(h.body.innerHTML,/不是 DAY 当日订单的寿命/);assert.match(h.body.innerHTML,/尚非经验证的回落买点/);assert.match(h.body.innerHTML,/历史参考 1 股 → 本次执行 6 股/);assert.match(h.body.innerHTML,/历史参考 1 股 → 本次执行 4 股/);assert.match(h.body.innerHTML,/data-accept/);
 assert.match(h.body.innerHTML,/<th>低于现价<\/th>/);
 for(const order of cash.preview.orders){
  const ref=cash.preview.rows.find(row=>row.security_id===order.security_id).reference;
  const expectedTime=new Date(ref.last_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  assert.ok(h.body.innerHTML.includes(expectedTime));
  const fraction=value=>{const [a,b='1']=value.split('/'),[whole,decimal='']=a.split('.');return [BigInt(whole+decimal),BigInt(b)*10n**BigInt(decimal.length)];};
  const [ln,ld]=fraction(ref.last_price),[pn,pd]=fraction(order.limit_price),delta=ln*pd-pn*ld;
  const bp=(delta<0n?-delta:delta)*10000n/(ln*pd);
  const expectedDelta=delta===0n?'持平':(delta<0n?'高于 ':'低于 ')+(bp/100n)+'.'+(bp%100n).toString().padStart(2,'0')+'%';
  assert.ok(h.body.innerHTML.includes('<td>'+expectedDelta+'</td>'),'display difference is computed from exact reference and limit fractions');

 }
 assert.match(h.body.innerHTML,/低于 \d+\.\d{2}%|持平/);

 assert.ok(h.body.innerHTML.includes('选股数据截至 '+cash.research.as_of));assert.ok(h.body.innerHTML.includes('报价交易日 '+cash.preview.rows[0].reference.session));assert.match(h.body.innerHTML,/最新价时间/);assert.match(h.body.innerHTML,/刷新报价不会重新选股/);
 const pullback=structuredClone(cash.preview),pullbackVersion='V2_OBSERVED_SESSION_REBOUND_PULLBACK_RESEARCH_V1';
 for(const row of pullback.rows){const ref=row.reference,binding={security_id:row.security_id,ticker:cash.research.stocks.find(s=>s.security_id===row.security_id).ticker,session:ref.session,currency:'USD',price_basis:'CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',policy_id:'a'.repeat(64)};
  ref.pullback={schema:pullbackVersion,policy:{version:pullbackVersion,rebound_fraction:'1/2',minimum_discount:'1/100',maximum_age_seconds:120},policy_id:binding.policy_id,binding,observed_session_low:'8',last_price:ref.last_price,rebound_level:'9',discount_level:'99/10',limit_price:'9',reference_valid_until:ref.refresh_by,hypothetical_day_expiry:ref.session_close,cap_declaration:{binding,observed_at:cash.now,limit_price:'9'},prior_cap:null,input_digest:'b'.repeat(64),cap_record_hash:'c'.repeat(64),status:'EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED',research_only:true,source_authenticated:false,performance_validated:false,orders_created:false};
 }
 let ph=await cashPreview(cash.research,pullback);assert.match(ph.body.innerHTML,/试运行回落价/);assert.match(ph.body.innerHTML,/观测日低点/);assert.match(ph.body.innerHTML,/\$8.00/);assert.match(ph.body.innerHTML,/月度调仓尚未迁移/);assert.doesNotMatch(ph.body.innerHTML,/旧参考规则/);assert.deepEqual(Object.keys(JSON.parse(ph.calls[0].options.body)),['decision_id']);
 const priorPullback=structuredClone(pullback);for(const row of priorPullback.rows)row.reference.pullback.prior_cap=structuredClone(row.reference.pullback.cap_declaration);
 ph=await cashPreview(cash.research,priorPullback);assert.match(ph.body.innerHTML,/试运行回落价/);
 const cappedPullback=structuredClone(priorPullback);for(const row of cappedPullback.rows){row.reference.pullback.observed_session_low='9';row.reference.pullback.rebound_level='19/2';}
 ph=await cashPreview(cash.research,cappedPullback);assert.match(ph.body.innerHTML,/试运行回落价/);
 const discountedPullback=structuredClone(pullback);for(const row of discountedPullback.rows){const x=row.reference.pullback;x.observed_session_low='9';x.rebound_level='19/2';x.policy.minimum_discount='1/10';x.discount_level='9';}
 ph=await cashPreview(cash.research,discountedPullback);assert.match(ph.body.innerHTML,/试运行回落价/);
 for(const modify of [x=>x.policy.rebound_fraction='1',x=>x.policy.minimum_discount='0',x=>x.policy.maximum_age_seconds=121,x=>x.last_price='11',x=>x.observed_session_low='7',x=>x.rebound_level='8',x=>x.discount_level='9',x=>x.limit_price='9.01',x=>x.binding.security_id='OTHER',x=>x.binding.policy_id='d'.repeat(64),x=>x.cap_record_hash='bad',x=>x.performance_validated=true,x=>x.reference_valid_until='2099-01-01T00:00:00Z',x=>x.cap_declaration.observed_at='2099-01-01T00:00:00Z',x=>x.prior_cap.binding.session='2026-10-14',x=>x.prior_cap.limit_price='8',x=>x.prior_cap.observed_at='2099-01-01T00:00:00Z']){
  const bad=structuredClone(priorPullback);modify(bad.rows[0].reference.pullback);ph=await cashPreview(cash.research,bad);assert.match(ph.body.innerHTML,/读取不可用/);assert.doesNotMatch(ph.body.innerHTML,/data-accept/);
 }
 p=h.c.accept();const cashPending=h.calls.at(-1).options.body;h.respond({},false);await p;assert.equal(JSON.parse(h.storage.getItem('quantity-v2-paper-pending-v1')).execution_target_id,cash.preview.execution_target_id);h.c.invalidate();
 let cashRestored=harness(h.storage);p=cashRestored.c.retry();assert.equal(cashRestored.calls.at(-1).options.body,cashPending);cashRestored.respond(cash.accepted);await p;cashRestored.c.setResearch(cash.research);p=cashRestored.c.restore();cashRestored.respond(cash.accepted);await p;assert.match(cashRestored.body.innerHTML,/暂不能续单/);const noContinuation=cashRestored.calls.length;cashRestored.c.continuation();assert.equal(cashRestored.calls.length,noContinuation);
 // Configured new-scope accounts retain execution lineage; open orders still prohibit a continuation.
 const enabledCash={...structuredClone(cash.accepted),capabilities:{continuation:{configured:true,reason:null,policy:"EXPLICIT_UNIT_REVIEW"}}};
 p=cashRestored.c.restore();cashRestored.respond(enabledCash);await p;const openCount=cashRestored.calls.length;cashRestored.c.continuation();assert.equal(cashRestored.calls.length,openCount);
 const closedCash=structuredClone(enabledCash);closedCash.orders.forEach(o=>o.closed='CANCEL');closedCash.reserved_cash='0';
 p=cashRestored.c.restore();cashRestored.respond(closedCash);await p;p=cashRestored.c.continuation();assert.equal(cashRestored.calls.at(-1).url,'/api/current_portfolio_research/paper_v2/continuation/preview');
 cashRestored.respond({...structuredClone(cf.proposal),account_id:closedCash.account_id,capital_decision_id:closedCash.capital_decision_id,research_id:closedCash.research_id,prior_revision:closedCash.revision,target_month:closedCash.target_month,target_scope:closedCash.target_scope,execution_target_id:'f'.repeat(64)});await p;assert.match(cashRestored.body.innerHTML,/读取不可用/);assert.doesNotMatch(cashRestored.body.innerHTML,/data-accept/);

 const cc=cash.continuation;
 cashRestored.setTime(Date.parse(cc.now));p=cashRestored.c.restore();cashRestored.respond(cc.closed);await p;
 p=cashRestored.c.continuation();cashRestored.respond(cc.proposal);await p;assert.match(cashRestored.body.innerHTML,/data-accept/);assert.match(cashRestored.body.innerHTML,/沿用本月目标/);
 const bounded={policy:'BOUNDED_PUBLIC_KNOWN_ACTIONS_V1',coverage_complete:false,source_authenticated:false,retention_unknown:true,limited_name_coverage:true,limitations:['可能漏报']};
 p=cashRestored.c.continuation();cashRestored.respond({...cc.proposal,unit_review:bounded});await p;assert.match(cashRestored.body.innerHTML,/可能漏报/);assert.match(cashRestored.body.innerHTML,/部分标的仅按代码匹配/);
 for(const change of [v=>v.coverage_complete=true,v=>v.source_authenticated=true,v=>v.policy='UNKNOWN',v=>delete v.retention_unknown]){const bad=structuredClone(bounded);change(bad);p=cashRestored.c.continuation();cashRestored.respond({...cc.proposal,unit_review:bad});await p;assert.doesNotMatch(cashRestored.body.innerHTML,/data-accept/);}
 for(const code of ['BOUNDED_PUBLIC_REVIEW_UNAVAILABLE','BOUNDED_UNIT_CHANGE_CANDIDATE']){p=cashRestored.c.continuation();cashRestored.respond({error_code:code},false);await p;assert.match(cashRestored.body.innerHTML,/暂停续单/);assert.doesNotMatch(cashRestored.body.innerHTML,/BOUNDED_/);}
 p=cashRestored.c.restore();cashRestored.respond(cash.accepted);await p;
 cashRestored.setTime(Date.parse(cash.fields.executed_at));p=cashRestored.c.record('FILL',cash.accepted.orders[0].order_id,cash.fields);cashRestored.respond(cash.filled);await p;assert.match(cashRestored.body.innerHTML,/100.80/);
 // Same decision/account but a different execution target can never be restored or accepted as this lineage.
 p=cashRestored.c.restore();cashRestored.respond({...cash.filled,execution_target_id:'f'.repeat(64)});await p;assert.match(cashRestored.body.innerHTML,/读取不可用/);const noWrite=cashRestored.calls.length;cashRestored.c.record('FILL',cash.accepted.orders[0].order_id,cash.fields);assert.equal(cashRestored.calls.length,noWrite);
 h=await cashPreview();p=h.c.accept();h.respond({...cash.accepted,execution_target_id:'f'.repeat(64)});await p;assert.match(h.body.innerHTML,/重试原操作/);assert.equal(h.storage.m.has('quantity-v2-paper-pending-v1'),true);
 for(const modify of [r=>delete r.frozen_dollar_allocations_exact,r=>r.frozen_dollar_allocations_exact.A='61']){let r=structuredClone(cash.research);modify(r);h=await cashPreview(r);assert.match(h.body.innerHTML,/读取不可用/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);}
 for(const modify of [p=>p.historical_target_quantities.A=2,p=>p.rows[0].current_quantity=1,p=>p.rows[0].frozen_dollar_allocation='61',p=>p.rows[0].allocation_residual='0',p=>p.rows[0].notional='0',p=>p.original_residual_cash='0',p=>p.remaining_cash='19',p=>p.target_quantities.A=1,p=>p.execution_target_id='bad',p=>p.current_execution_bytes_verified=false,p=>p.source_bytes_verified=true,p=>p.ledger_acceptance_supported=false,p=>p.orders[0].quantity=1]){let bad=structuredClone(cash.preview);modify(bad);h=await cashPreview(cash.research,bad);assert.match(h.body.innerHTML,/读取不可用/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);}
 // Real server quote package too expensive for one share returns KEEP_CASH/null proposal.
 h=await cashPreview(cash.research,cash.keep);assert.doesNotMatch(h.body.innerHTML,/data-accept/);assert.match(h.body.innerHTML,/保持现金/);
 // A high limit cannot pass by changing quantities and all cash arithmetic consistently.
 const high=structuredClone(cash.preview);high.rows[0].limit_price='11';high.rows[0].current_quantity=5;high.rows[0].notional='55';high.rows[0].allocation_residual='5';high.orders[0].limit_price='11';high.orders[0].quantity=5;high.target_quantities.A=5;high.reserved_buy_cash='91';high.remaining_cash='19';h=await cashPreview(cash.research,high);assert.match(h.body.innerHTML,/读取不可用/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);
 const stale=structuredClone(cash.preview);stale.rows[0].reference.refresh_by=cash.now;h=await cashPreview(cash.research,stale);assert.match(h.body.innerHTML,/读取不可用/);
 // Refresh retains the last display but immediately forbids acceptance, even before expiry.
 h=harness();await preview(h);p=h.c.preview();assert.match(h.body.innerHTML,/<strong>\$8.00<\/strong>/);assert.match(h.body.innerHTML,/待刷新/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);let beforeAccept=h.calls.length;h.c.accept();assert.equal(h.calls.length,beforeAccept);
 h.respond({reason:'SOURCE_UNAVAILABLE'},false);await p;assert.match(h.body.innerHTML,/<strong>\$8.00<\/strong>/);assert.doesNotMatch(h.body.innerHTML,/data-accept/);h.c.accept();assert.equal(h.calls.length,beforeAccept);
 p=h.c.preview();h.respond(fixture.preview);await p;assert.match(h.body.innerHTML,/data-accept/);assert.doesNotMatch(h.body.innerHTML,/data-stale-proposal/);
 // A verified no-order result replaces the prior actionable display.
 h=await cashPreview(cash.research,cash.preview);p=h.c.preview();h.respond(cash.keep);await p;assert.doesNotMatch(h.body.innerHTML,/<strong>|data-accept|data-stale-proposal/);assert.match(h.body.innerHTML,/保持现金/);
 h=harness();await preview(h);p=h.c.preview();h.c.setResearch({...fixture.research,available_cash_exact:'200'});h.respond(fixture.preview);await p;assert.doesNotMatch(h.body.innerHTML,/<strong>|data-accept/);
 console.log('PASS V2 paper: actual Python sourcebridge/ledger fixtures; manual initial and continuation preview/accept/fill/cancel/expiry; persisted exact retry/reload; identity, expiry, invalidation, late reads and storage failure; no live account/network');
})().catch(e=>{console.error(e);process.exitCode=1;});
