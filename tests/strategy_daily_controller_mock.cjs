'use strict';
// All cash fixtures are synthetic; no broker balance or transfer amount is used.
const assert=require('node:assert/strict');
const {waitingExplanation,createController,httpDependencies,fetchTransport,presentation,render,dollars,actionExplanation}=require('../web/strategy_daily_controller.js');
for(const reason of ['STALE_SNAPSHOT','STALE_REVISION','STALE_TARGET'])assert.match(waitingExplanation(reason),/无需重复录入新增资金/);
const clone=structuredClone;
const now=Date.parse('2026-10-20T15:00:00Z');
const quote={reference_valid_until:'2026-10-20T15:02:00Z',buy:10,sell:11};
function fixture(month='2026-10'){
 let account={revision:'revision-one',holdings:[{security_id:'S',ticker:'SNDK',quantity:14}]};
 let target=month?{target_id:'target-one',target_month:month,server_month:'2026-10',targets:[{security_id:'S',ticker:'SNDK',quantity:21}]}:{server_month:'2026-10'};
 const calls=[];
 const f={calls,now:()=>now,setAccount:x=>account=x,setTarget:x=>target=x,
  loadAccount:async()=>clone(account),loadTarget:async()=>clone(target),
  saveCash:async body=>{calls.push(['cash',body]);account.revision='revision-two';return clone(account);},
  generateTarget:async body=>{calls.push(['generate',body]);target={...target,target_id:'target-two',target_month:'2026-10'};return clone(target);},
  previewDaily:async body=>{calls.push(['daily',body]);return {status:'HOLD',account_revision:body.expected_revision,target_id:body.target_id,daily_gate:{rows:[{security_id:'S',action:'HOLD',effective_target:14}]},new_orders:[],reference_quotes:{}};}};
 return f;
}
(async()=>{
 let count=0;
 // An order cannot extend its source quote or survive a missing source.
 for(const source of ['expired','missing']){
  const f=fixture();
  f.previewDaily=async b=>({status:'READY',account_revision:b.expected_revision,target_id:b.target_id,
   daily_gate:{rows:[{security_id:'S',action:'SELL'}]},
   reference_quotes:source==='missing'?{}:{S:{...quote,reference_valid_until:new Date(now-1).toISOString()}},
   new_orders:[{security_id:'S',side:'SELL',quantity:4,limit_price:'11',reference_valid_until:quote.reference_valid_until}]});
  const c=createController(f);await c.refresh();
  const view=presentation(c.getState(),now);
  assert.equal(view.rows[0].orders.length,0,'source must remain valid: '+source);
  assert.equal(view.status,'WAIT_FRESH_SIGNAL');count++;
 }
 // A quote can expire during network transit. Keep the returned price only
 // as history and explain the need to refresh instead of showing empty READY.
 {
  const f=fixture();let clock=now;f.now=()=>clock;
  f.previewDaily=async b=>{
   clock=Date.parse(quote.reference_valid_until)+1;
   return {status:'READY',account_revision:b.expected_revision,target_id:b.target_id,
    daily_gate:{rows:[{security_id:'S',action:'SELL'}]},reference_quotes:{S:quote},
    new_orders:[{security_id:'S',side:'SELL',quantity:4,limit_price:'11',reference_valid_until:quote.reference_valid_until}]};
  };
  const c=createController(f);await c.refresh();
  const view=presentation(c.getState(),clock);
  assert.equal(view.status,'WAIT_FRESH_SIGNAL');
  assert.equal(view.rows[0].orders.length,0);
  assert.equal(view.rows[0].historical_orders[0].limit_price,'11');
  assert.equal(view.rows[0].historical_orders[0].executable,false);
  assert.equal(f.calls.filter(x=>x[0]==='cash').length,0);count++;
 }
 for(const month of ['2026-10',null,'2026-09']){
  const f=fixture(month),c=createController(f);
  await c.saveBalance({amount:'10234.56'});
  const generates=f.calls.filter(x=>x[0]==='generate');
  assert.equal(generates.length,month==='2026-10'?0:1);
  if(generates.length)assert.equal(generates[0][1].reason,month?'MONTHLY_SELECTION':'INITIAL');
  assert.equal(f.calls.at(-1)[0],'daily');assert.equal(c.getState().daily.status,'HOLD');count++;
 }
 // A later revision while a quote request is in flight invalidates its result.
 {
  const f=fixture();f.previewDaily=async body=>{f.setAccount({revision:'revision-new',holdings:[]});return {status:'HOLD',account_revision:body.expected_revision,target_id:body.target_id};};
  const c=createController(f);await assert.rejects(c.refresh(),/SNAPSHOT_CHANGED/);
  assert.equal(c.getState().daily,null);count++;
 }
 {
  const f=fixture();f.previewDaily=async body=>{f.setTarget({server_month:'2026-10',target_month:'2026-10',target_id:'changed'});return {status:'HOLD',account_revision:body.expected_revision,target_id:body.target_id};};
  await assert.rejects(createController(f).refresh(),/SNAPSHOT_CHANGED/);count++;
 }
 {
  const f=fixture();let resolve;
  f.previewDaily=()=>new Promise(r=>resolve=r);
  const c=createController(f),pending=c.refresh();
  while(!resolve)await new Promise(r=>setImmediate(r));
  c.invalidate();resolve({});
  await assert.rejects(pending,/DAILY_UI_SNAPSHOT_CHANGED/);assert.equal(c.getState().daily,null);count++;
 }
 {
  const f=fixture();f.previewDaily=async b=>({status:'WAIT_SIGNAL',account_revision:b.expected_revision,target_id:b.target_id,reference_quotes:{S:quote}});
  await assert.rejects(createController(f).refresh(),/WAIT_MUST_NOT/);count++;
 }
 // Mixed sell + WAIT never turns the blocked buy into a visible executable price.
 {
  const model={account:{revision:'r',holdings:[{security_id:'S',quantity:14}]},target:{target_id:'t',targets:[{security_id:'S',quantity:21}]},historicalQuotes:{S:quote},
   daily:{status:'CONDITIONAL_PREVIEW_READY',account_revision:'r',target_id:'t',effective_target_quantities:{S:10,B:3},
   daily_gate:{rows:[{security_id:'S',action:'SELL'},{security_id:'B',action:'WAIT'}]},
   reference_quotes:{S:quote,B:quote},new_orders:[{security_id:'S',side:'SELL',quantity:4,reference_valid_until:quote.reference_valid_until},{security_id:'B',side:'BUY',quantity:3,reference_valid_until:quote.reference_valid_until}]}};
  let p=presentation(model,now),s=p.rows.find(x=>x.security_id==='S'),b=p.rows.find(x=>x.security_id==='B');
  assert.equal(s.action,'SELL');assert.equal(s.monthly_target,21);assert.equal(s.daily_effective_target,10);
  assert.equal(s.orders.length,1);assert.equal(b.orders.length,0);assert.equal(b.quotes,null);
  p=presentation(model,now+180000);s=p.rows.find(x=>x.security_id==='S');
  assert.equal(s.action,'WAIT');assert.equal(s.orders.length,0);assert.equal(s.historical_quote.executable,false);
  count++;
 }
 {
  for(const landed of [false,true]){
   let a={revision:'a'.repeat(64),holdings:[]},t={server_month:'2026-10'},cashWrites=0,first=true;
   const bodies=[],operations=new Map();
   const request=async(path,body)=>{
    if(path==='/api/strategy-account')return {account:clone(a)};
    if(path.endsWith('/target'))return clone(t);
    if(path.endsWith('/generate')){
     assert.deepEqual(Object.keys(body).sort(),['event_id','expected_revision','previous_target_id','reason']);
     bodies.push(clone(body));
     if(operations.has(body.event_id)){assert.deepEqual(operations.get(body.event_id).body,body);return clone(operations.get(body.event_id).result);}
     const commit=()=>{t={server_month:'2026-10',target_month:'2026-10',target_id:'c'.repeat(64),targets:[]};operations.set(body.event_id,{body:clone(body),result:clone(t)});};
     if(first){first=false;if(landed)commit();throw Error('NETWORK_RESPONSE_LOST');}
     commit();return clone(t);
    }
    return {status:'WAIT',account_revision:a.revision,target_id:t.target_id,new_orders:[],reference_quotes:{}};
   };
   const account={getState:()=>({account:clone(a)}),confirmCash:async()=>{cashWrites++;a.revision='b'.repeat(64);return {account:clone(a)};}};
   const c=createController(httpDependencies(request,()=> 'stable-operation',account));
   await assert.rejects(c.saveBalance({amount:'50'}),/NETWORK_RESPONSE_LOST/);
   await assert.rejects(c.saveBalance({amount:'60'}),/TARGET_WRITE_RECONCILIATION_REQUIRED/);
   assert.equal(cashWrites,1);
   await c.refresh();assert.equal(c.getState().daily.status,'WAIT');
   assert.deepEqual(bodies[0],bodies[1]);assert.equal(cashWrites,1);
   await c.saveBalance({amount:'60'});assert.equal(cashWrites,2);
   count++;
  }
 }
 {
  const f=fixture(null);let stage=0,cashWrites=0;
  const request=fetchTransport(async(path,options)=>{
   const body=options?.body?JSON.parse(options.body):null;
   if(stage===0){stage++;throw Error('NETWORK');}
   if(stage===1){stage++;return {ok:false,status:409,json:async()=>({status:'BLOCKED',reason:'STALE_REVISION'})};}
   return {ok:true,status:200,json:async()=>({target_id:'target-new'})};
  });
  const deps=httpDependencies(request,()=> 'event',null);
  const c=createController({...f,saveCash:async b=>{cashWrites++;return f.saveCash(b);},generateTarget:deps.generateTarget});
  await assert.rejects(c.saveBalance({amount:'1'}),/NETWORK/);
  await assert.rejects(c.refresh(),/STALE_REVISION/);
  // A definite no-commit response releases both locks. No extra cash write was
  // made during reconciliation; the next explicit user save can proceed.
  assert.equal(cashWrites,1);
  await assert.rejects(c.saveBalance({amount:'2'}),/TARGET_CHANGED_AFTER_GENERATION/);
  assert.equal(cashWrites,2);count++;
 }
 {
  const f=fixture();
  let preview=async b=>({status:'CONDITIONAL_PREVIEW_READY',account_revision:b.expected_revision,target_id:b.target_id,daily_gate:{rows:[{security_id:'S',action:'BUY'}]},reference_quotes:{S:quote},new_orders:[]});
  const c=createController({...f,previewDaily:b=>preview(b)});
  await c.refresh();
  preview=async b=>({status:'WAIT_POLICY_RELEASE',account_revision:b.expected_revision,target_id:b.target_id,new_orders:[],reference_quotes:{}});
  await c.refresh();
  assert.equal(presentation(c.getState(),now).rows[0].historical_quote.executable,false);count++;
 }
 {
  const {createController:createAccount}=require('../web/strategy_account.js');
  let account={revision:'a'.repeat(64),holdings:[],orders:[],cash_confirmation_valid:true};
  let target={server_month:'2026-10'},daily,uncertain=false,posts=0;
  const requests=[];
  const request=async(path,body)=>{
   requests.push({path,body});
   if(path.endsWith('/valuation'))return {status:'READY',account_revision:account.revision,holdings:[]};
   if(path.endsWith('/events')){
    posts++;assert.deepEqual(Object.keys(body).sort(),['event','expected_revision']);
    assert.deepEqual(Object.keys(body.event).sort(),['amount','cash_basis','event_id','kind']);
    assert.equal(body.event.amount,'10234.56');
    if(uncertain)return {status:'BLOCKED',reconcile_before_retry:true};
    account={...account,revision:'b'.repeat(64)};return {status:'READY',account:clone(account)};
   }
   if(path.endsWith('/generate')){
    assert.deepEqual(Object.keys(body).sort(),['event_id','expected_revision','previous_target_id','reason']);
    assert.match(body.event_id,/^[A-Za-z0-9_.:-]{1,128}$/);
    target={server_month:'2026-10',target_month:'2026-10',target_id:'c'.repeat(64),targets:[]};
    return clone(target);
   }
   if(path==='/api/strategy-daily-v3/preview'){
    assert.deepEqual(Object.keys(body).sort(),['expected_revision','target_id']);
    return {status:'WAIT',detail_status:'WAIT_POLICY_RELEASE',account_revision:account.revision,target_id:target.target_id,new_orders:[],reference_quotes:{}};
   }
   if(path.endsWith('/target'))return clone(target);
   return {status:'READY',account:clone(account)};
  };
  const realAccount=createAccount({fetchImpl:async(path,options)=>({ok:true,json:()=>request(path,options?.body?JSON.parse(options.body):undefined)}),makeId:()=> 'cash-event-1',onInvalidate:()=>daily?.accountInvalidated()});
  await realAccount.load();
  daily=createController(httpDependencies(request,()=> 'target-event-1',realAccount));
  await daily.saveBalance({amount:'10,234.56'});
  assert.equal(daily.getState().cashSaved,true);assert.equal(daily.getState().daily.status,'WAIT');
  assert(requests.some(x=>x.path==='/api/strategy-daily-v3/preview'));
  uncertain=true;
  await assert.rejects(daily.saveBalance({amount:'10,234.56'}),/RECONCILE_REQUIRED/);
  const before=posts;
  await assert.rejects(daily.saveBalance({amount:'10,234.56'}),/ACCOUNT_CONTROLLER_RELOAD_REQUIRED|RECONCILE_REQUIRED/);
  assert.equal(posts,before);count++;
 }
 {
  const f=fixture();
  f.previewDaily=async()=>{throw Error('QUOTE_UNAVAILABLE');};
  const c=createController(f);
  await assert.rejects(c.saveBalance({amount:'50'}),/QUOTE_UNAVAILABLE/);
  assert.equal(c.getState().cashSaved,true);assert.equal(f.calls.filter(x=>x[0]==='cash').length,1);count++;
 }
 {
  const attempts=[];let attempt=0;
  const deps=httpDependencies(async(path,body)=>{attempts.push(body);if(attempt++===0)throw Error('NETWORK');return {target_id:'t'};},()=> 'stable-target-event');
  const body={expected_revision:'r',previous_target_id:null,reason:'INITIAL'};
  await assert.rejects(deps.generateTarget(body),/NETWORK/);
  await deps.generateTarget(body);
  assert.deepEqual(attempts[0],attempts[1]);count++;
 }
 {
  const f=fixture();f.previewDaily=async b=>({status:'READY',detail_status:'CONDITIONAL_SELL_PREVIEW_BUYS_WAIT',account_revision:b.expected_revision,target_id:b.target_id,daily_gate:{rows:[{security_id:'S',action:'SELL'}]},effective_target_quantities:{S:10},reference_quotes:{S:quote},new_orders:[{security_id:'S',side:'SELL',quantity:4,limit_price:'11',reference_valid_until:quote.reference_valid_until}]});
  const c=createController(f);await c.refresh();
  assert.equal(presentation(c.getState(),now).rows[0].action,'SELL');count++;
 }
 {
  const doc={createElement:tag=>({tag,children:[],textContent:'',appendChild(x){this.children.push(x);}})};
  const container={ownerDocument:doc,replaceChildren(...xs){this.children=xs;}};
  render(container,{account:{revision:'r',holdings:[{security_id:'S',ticker:'SNDK',quantity:14}]},target:null,daily:null,historicalQuotes:{S:quote}},now);
  const texts=node=>[node.textContent||'',...(node.children||[]).flatMap(texts)];
  const output=texts(container).join(' ');
  assert.match(output,/本月目标/);assert.match(output,/今日有效目标/);assert.match(output,/上一条建议/);
  assert.match(output,/买入 \$10.00/);assert.match(output,/卖出 \$11.00/);
  assert(!output.includes('<details'));count++;
 }
 {
  const f=fixture();let side='SELL',quantity=4,price='11',broken=false;
  f.previewDaily=async b=>{
   if(broken)throw Error('NETWORK');
   return {status:'READY',account_revision:b.expected_revision,target_id:b.target_id,
    daily_gate:{rows:[{security_id:'S',action:side}]},reference_quotes:{S:quote},
    new_orders:[{security_id:'S',side,quantity,limit_price:price,reference_valid_until:quote.reference_valid_until}]};
  };
  const c=createController(f);await c.refresh();
  let row=presentation(c.getState(),now+120000).rows[0];
  assert.equal(row.action,'WAIT');assert.equal(row.orders.length,0);
  assert.deepEqual(row.historical_orders.map(o=>[o.side,o.quantity,o.limit_price,o.executable]),[['SELL',4,'11',false]]);
  broken=true;await assert.rejects(c.refresh(),/NETWORK/);
  row=presentation(c.getState(),now).rows[0];
  assert.equal(row.orders.length,0);assert.equal(row.historical_orders[0].side,'SELL');
  c.accountInvalidated();
  assert.equal(presentation(c.getState(),now).rows[0].historical_orders[0].quantity,4);
  broken=false;side='BUY';quantity=2;price='9';await c.refresh();
  row=presentation(c.getState(),now).rows[0];
  assert.equal(row.orders[0].side,'BUY');assert.equal(row.orders[0].quantity,2);
  assert.equal(row.historical_orders.length,0);
  c.invalidate();row=presentation(c.getState(),now).rows[0];
  assert.equal(row.historical_orders.length,1);assert.equal(row.historical_orders[0].side,'BUY');
  // A gate-denied row is never admitted to either current or historical orders.
  side='WAIT';await c.refresh();c.invalidate();
  row=presentation(c.getState(),now).rows[0];
  assert.equal(row.orders.length,0);assert.equal(row.historical_orders.length,1);
  assert.equal(row.historical_orders[0].side,'BUY');count++;
 }
 {
  const model={account:{holdings:[{security_id:'S',ticker:'MRNA',quantity:0}]},target:null,daily:{waiting_data:[{security_id:'S'}]},historicalOrders:{S:[{side:'BUY',quantity:49,limit_price:'222.59'}]}};
  const doc={createElement:tag=>({tag,children:[],textContent:'',style:{},appendChild(x){this.children.push(x);}})};
  const container={ownerDocument:doc,replaceChildren(...xs){this.children=xs;}};
  render(container,model,now);
  const texts=node=>[node.textContent||'',...(node.children||[]).flatMap(texts)];
  const output=texts(container).join(' ');
  assert.match(output,/分钟行情缺失/);assert(!output.includes('222.59'));count++;
 }
 for(const [reason,expected] of [['HALT_ACTIVE_OR_RESUME_UNCONFIRMED',/尚未确认复牌/],['POST_RESUMPTION_COMPLETE_BAR_REQUIRED',/复牌后的完整成交分钟/],['HALT_EXECUTION_EVIDENCE_REQUIRED',/停复牌信息暂未核验/]]){
  const text=actionExplanation({security_id:'S',orders:[],historical_orders:[]},{},{daily:{waiting_data:[{security_id:'S',data_failure:reason}]}});
  assert.match(text,expected);count++;
 }
 // A server/proxy plain-text 500 after saving cash must invalidate the old
 // executable advice. Retrying only the preview must not write cash again.
 {
  const f=fixture();let unavailable=false;
  const request=fetchTransport(async(path,options)=>({ok:!unavailable,status:unavailable?500:200,
   json:async()=>{
    if(unavailable)throw new SyntaxError('Unexpected token I: Internal Server Error');
    const body=JSON.parse(options.body);
    return {status:'READY',account_revision:body.expected_revision,target_id:body.target_id,
     daily_gate:{rows:[{security_id:'S',action:'BUY'}]},reference_quotes:{S:quote},
     new_orders:[{security_id:'S',side:'BUY',quantity:7,limit_price:'10',reference_valid_until:quote.reference_valid_until}]};
   }}));
  f.previewDaily=body=>request('/api/strategy-daily-v3/preview',body);
  const c=createController(f);await c.refresh();
  assert.equal(presentation(c.getState(),now).rows[0].orders.length,1);
  unavailable=true;
  await assert.rejects(c.saveBalance({amount:'10234.56'}),/^Error: DAILY_RESPONSE_UNAVAILABLE$/);
  assert.equal(c.getState().cashSaved,true);
  assert.equal(presentation(c.getState(),now).rows[0].orders.length,0);
  assert.equal(f.calls.filter(x=>x[0]==='cash').length,1);
  unavailable=false;await c.refresh();
  assert.equal(presentation(c.getState(),now).rows[0].orders.length,1);
  assert.equal(f.calls.filter(x=>x[0]==='cash').length,1);count++;
 }
 // Proxies can return syntactically valid JSON with no response envelope.
 // Do not leak a TypeError or treat an array/scalar as successful advice.
 for(const value of [null,[],42,'Internal Server Error',true]){
  const request=fetchTransport(async()=>({ok:true,status:200,json:async()=>value}));
  await assert.rejects(request('/api/strategy-daily-v3/preview',{}),/^Error: DAILY_RESPONSE_UNAVAILABLE$/);count++;
 }
 {
  const row={security_id:'S',held:14,monthly_target:13,daily_effective_target:6,orders:[{side:'SELL',quantity:8}]};
  const note={policy:'SMA20_HALF_OFF_RESEARCH',signal_date:'2026-10-21',above_sma20:false,monthly_target:13,effective_target:6};
  const model={daily:{signal_explanations:{S:note}}};
  assert.match(actionExplanation(row,{},model),/2026-10-21 收盘不高于20日均线.*减半并向下取整.*减仓 8/);
  note.effective_target=7;
  assert(!actionExplanation(row,{},model).includes('20日均线'));
  note.effective_target=6;note.policy='other';
  assert(!actionExplanation(row,{},model).includes('20日均线'));count++;
 }
 // Mixed sell/buy responses keep waiting_cash at top level; an old order
 // must not hide the fresh reason that the new buy is waiting for cash.
 {
  const row={security_id:'B',orders:[],historical_orders:[{side:'BUY'}],action:'WAIT'};
  assert.match(actionExplanation(row,{}, {daily:{waiting_cash:[{security_id:'B',quantity:5}]}}),/可用现金不足.*未成交卖款/);
  assert.match(actionExplanation({...row,reason:'PENDING_RECONCILIATION_REQUIRED'}, {}, {daily:{}}),/已有未成交挂单/);
  assert.match(actionExplanation({...row,reason:'NO_AVAILABLE_CASH'}, {}, {daily:{}}),/可用现金不足/);
  assert.match(actionExplanation(row,{}, {daily:{}}),/上一条建议已失效/);count++;
 }
 assert.equal(dollars('13668/10'),'$1,366.80');assert.equal(dollars('1/0'),'—');
 assert.equal(dollars('1322.21'),'$1,322.21');count++;
 console.log(`${count} daily controller scenarios PASS`);
})().catch(error=>{console.error(error);process.exitCode=1;});
