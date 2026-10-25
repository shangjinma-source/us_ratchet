(function(root){
'use strict';
// UI orchestration only; server configuration owns strategy enablement.
const copy=x=>structuredClone(x);
const fail=message=>{throw new Error(message);};
const allowed=new Set(['READY','WAIT','DAILY_PREVIEW_DISABLED','WAIT_POLICY_RELEASE','WAIT_SIGNAL',
 'WAIT_FRESH_SIGNAL','WAIT_MONTHLY_TARGET','WAIT_PENDING_RECONCILIATION',
 'WAIT_EXECUTION_ELIGIBILITY','HOLD','CONDITIONAL_PREVIEW_READY']);
function waitingExplanation(reason){
 if(reason==='CASH_INPUT_SNAPSHOT_CHANGED')return '账户余额已变化，本次输入未覆盖账户。请核对当前余额后再点击查看建议。';
 if(reason==='WAIT_CALENDAR_SESSION')return '当前不在策略交易时段，等待下一交易时段后更新建议。';
 if(['STALE_SNAPSHOT','STALE_REVISION','STALE_TARGET','SUPPLEMENT_SNAPSHOT_CHANGED',
     'RISK_SUPPLEMENT_SNAPSHOT_CHANGED','SNAPSHOT_CHANGED_DURING_PREVIEW',
     'TARGET_CHANGED_AFTER_GENERATION','DAILY_UI_SNAPSHOT_CHANGED'].includes(reason))return '账户余额或月度目标已更新，本次请求使用了旧版本。请点击右上角“刷新”读取最新状态，再查看建议；无需重复录入新增资金。';
 if(reason==='COMPLETE_MINUTES_REQUIRED')return '等待完整的1分钟行情；开盘首分钟结束后请重试，暂不生成买卖建议。';
 if(reason==='RECONCILE_REQUIRED')return '现金保存结果待核对，请先点击页面右上角“刷新”，勿重复提交。';
 if(reason==='WAIT_POLICY_REVIEW_SESSION')return '等待美股正式开盘；开盘后点击“更新现金并查看建议”获取当次判断。';
 if(reason==='OFFICIAL_ACTION_SOURCE_UNAVAILABLE')return '公告数据源暂不可用，本次未生成新建议；请稍后重试，旧建议不可用于挂单。';
 if(reason==='INCOMPLETE_MARK_DOMAIN')return '最新报价未通过核验；请检查电脑时间同步及行情连接。旧价格不可用于挂单。';
 if(reason==='DAILY_REQUEST_TIMEOUT')return '请求超时，本次建议未更新；请再次点击查看建议，旧价格不可用于挂单。';
 if(reason==='DAILY_RESPONSE_UNAVAILABLE')return '行情服务暂时返回异常，本次建议未更新；旧价格不可用于挂单。';
 if(['RSS_PUBLICATION_TIME_INVALID','ACTION_RSS_TIME_INVALID'].includes(reason))return '公告源时间核验失败，当前没有新的买卖建议；旧价格不可用于挂单。';
 return ({WAIT_NEW_SESSION_EVIDENCE:"等待当日数据核验，暂不生成买卖建议",DOMAIN_POLICY_AUTHORIZATION_TIME:"等待策略有效时段，暂不生成买卖建议",DAILY_TARGET_SELECTOR_PROFILE_MISMATCH:"等待本月目标完成策略升级，暂不生成买卖建议"})[reason]||null;
}
function createController({loadAccount,loadTarget,saveCash,generateTarget,previewDaily,onChange=()=>{},now=()=>Date.now()}){
 let epoch=0,ownCashStart=false,pendingTargetRequest=null,invalidationGeneration=0;
 let workTail=Promise.resolve(),writeBarrier=0,lastWrite=null;
 const pendingReads=new Map(),pendingSaves=new Map();
 function schedule(kind,operation,input){
  const writes=kind==='save';
  const inputKey=writes?JSON.stringify(input):null;
  if(writes&&lastWrite?.inputKey===inputKey&&pendingSaves.has(lastWrite.key))return pendingSaves.get(lastWrite.key);
  if(writes)++writeBarrier;
  const readSuffix=writeBarrier+':'+invalidationGeneration;
  const key=writes?kind+':'+writeBarrier:kind+':'+readSuffix;
  const pending=writes?pendingSaves:pendingReads;
  if(!writes&&kind==='load'&&pendingReads.has('refresh:'+readSuffix))return pendingReads.get('refresh:'+readSuffix);
  if(pending.has(key))return pending.get(key);
  if(writes)lastWrite={key,inputKey};
  const submittedGeneration=invalidationGeneration;
  const promise=workTail.then(()=>{
   if(writes&&submittedGeneration!==invalidationGeneration)fail('DAILY_UI_SNAPSHOT_CHANGED');
   return transact(operation);
  });
  pending.set(key,promise);
  workTail=promise.then(()=>{},()=>{});
  promise.then(()=>{if(pending.get(key)===promise)pending.delete(key);},()=>{if(pending.get(key)===promise)pending.delete(key);});
  return promise;
 }
 const model={account:null,target:null,daily:null,historicalQuotes:{},historicalOrders:{},busy:false,error:null,cashSaved:false};
 const notify=()=>onChange(copy(model));
 function retire(){
  const admitted=order=>(model.daily?.daily_gate?.rows||[]).some(row=>row.security_id===order.security_id&&row.action===order.side&&['BUY','SELL'].includes(row.action));
  for(const [sid,quote] of Object.entries(model.daily?.reference_quotes||{})){
   if((model.daily.daily_gate?.rows||[]).some(row=>row.security_id===sid&&['BUY','SELL'].includes(row.action)))model.historicalQuotes[sid]=copy(quote);
  }
  for(const sid of new Set((model.daily?.new_orders||[]).filter(admitted).map(order=>order.security_id))){
   model.historicalOrders[sid]=copy(model.daily.new_orders.filter(order=>order.security_id===sid&&admitted(order)));
  }
  model.daily=null;
 }
 const guard=token=>{if(token!==epoch)fail('DAILY_UI_SNAPSHOT_CHANGED');};
 function acceptDaily(value){
  if(!value||value.account_revision!==model.account?.revision||value.target_id!==model.target?.target_id)fail('DAILY_RESPONSE_BINDING_MISMATCH');
  if(!allowed.has(value.status))fail('DAILY_STATUS_NOT_ADMITTED');
  if(!['READY','CONDITIONAL_PREVIEW_READY'].includes(value.status)&&((value.new_orders||[]).length||Object.keys(value.reference_quotes||{}).length))fail('WAIT_MUST_NOT_CONTAIN_EXECUTABLE_QUOTES');
  value=copy(value);
  const gate=sid=>(value.daily_gate?.rows||[]).find(row=>row.security_id===sid)?.action;
  const admittedQuotes=Object.fromEntries(Object.entries(value.reference_quotes||{}).filter(([sid,quote])=>
   ['BUY','SELL'].includes(gate(sid))&&Number.isFinite(Date.parse(quote.reference_valid_until))));
  // Keep expired arrivals as evidence. presentation() decides executability
  // using the current clock and renders these solely as historical prices.
  value.new_orders=(value.new_orders||[]).filter(order=>gate(order.security_id)===order.side&&
   ['BUY','SELL'].includes(order.side)&&Number.isFinite(Date.parse(order.reference_valid_until||admittedQuotes[order.security_id]?.reference_valid_until)));
  value.reference_quotes=admittedQuotes;
  for(const sid of new Set([...Object.keys(value.reference_quotes||{}),...(value.new_orders||[]).map(order=>order.security_id)])){
   delete model.historicalQuotes[sid];delete model.historicalOrders[sid];
  }
  model.daily=copy(value);
 }
 async function transact(operation){
  if(model.busy)fail('DAILY_UI_BUSY');
  const token=++epoch;model.busy=true;model.error=null;retire();notify();
  try{return await operation(token);}
  catch(error){if(token===epoch){retire();model.error=error.message;}throw error;}
  finally{if(token===epoch){model.busy=false;notify();}}
 }
 async function requestDaily(token){
  guard(token);
  if(!model.target?.target_id)fail('MONTHLY_TARGET_REQUIRED');
  const binding={expected_revision:model.account.revision,target_id:model.target.target_id};
  const response=await previewDaily(binding);guard(token);
  await read(token);
  if(model.account.revision!==binding.expected_revision||model.target?.target_id!==binding.target_id)fail('SNAPSHOT_CHANGED_DURING_PREVIEW');
  acceptDaily(response);
  return copy(model);
 }
 async function read(token){
  const [account,target]=await Promise.all([loadAccount(),loadTarget()]);
  guard(token);
  if(!account?.revision)fail('ACCOUNT_REQUIRED');
  if(!target?.server_month)fail('SERVER_MONTH_REQUIRED');
  model.account=copy(account);model.target=target.target_id?copy(target):null;
  return target.server_month;
 }
 async function finishTargetRequest(token){
  // Replay the exact server-idempotent operation after reading current state.
  // Seeing any target is insufficient proof that our operation succeeded.
  const request=copy(pendingTargetRequest);
  let generated;
  try{generated=await generateTarget(request);}
  catch(error){
   if(error.target_not_committed===true){pendingTargetRequest=null;await read(token);}
   throw error;
  }
  guard(token);
  if(!generated?.target_id)fail('TARGET_GENERATION_REQUIRED');
  pendingTargetRequest=null;
  await read(token);
  if(model.account.revision!==request.expected_revision||model.target?.target_id!==generated.target_id)fail('TARGET_CHANGED_AFTER_GENERATION');
 }
 return {
  getState:()=>copy(model),
  accountInvalidated(){
   if(ownCashStart){retire();notify();return;}
   ++invalidationGeneration;++epoch;retire();model.busy=false;model.error='DAILY_UI_SNAPSHOT_CHANGED';notify();
  },
  // Called by account/holding events in the surrounding page. Pending responses
  // become unusable; stale orders are retained only as historical references.
  invalidate(){++invalidationGeneration;++epoch;retire();model.busy=false;model.error='DAILY_UI_SNAPSHOT_CHANGED';notify();},
  load(){return schedule('load',async token=>{await read(token);return copy(model);});},
  refresh(){return schedule('refresh',async token=>{await read(token);if(pendingTargetRequest)await finishTargetRequest(token);return requestDaily(token);});},
  saveBalance(input){input=copy(input);return schedule('save',async token=>{
   if(pendingTargetRequest)fail('TARGET_WRITE_RECONCILIATION_REQUIRED');
   await read(token);
   model.cashSaved=false;
   const previous=model.account.revision;
   if(input.expected_revision!==undefined&&input.expected_revision!==previous)fail('CASH_INPUT_SNAPSHOT_CHANGED');
   let pending;
   // Existing account.confirmCash synchronously invalidates before its first
   // await. Ignore only that call-stack notification, never later fill events.
   ownCashStart=true;
   try{pending=saveCash({...copy(input),expected_revision:previous,cash_basis:'AVAILABLE_AFTER_RESERVATIONS'});}
   finally{ownCashStart=false;}
   const updated=await pending;
   guard(token);
   if(!updated?.revision)fail('CASH_SAVE_REVISION_REQUIRED');
   model.cashSaved=true;
   const savedRevision=updated.revision;
   const serverMonth=await read(token);
   if(model.account.revision!==savedRevision)fail('ACCOUNT_CHANGED_AFTER_CASH_SAVE');
   let reason=null;
   if(!model.target)reason='INITIAL';
   else if(model.target.target_month<serverMonth)reason='MONTHLY_SELECTION';
   else if(model.target.target_month>serverMonth)fail('FUTURE_MONTHLY_TARGET');
   // Ordinary balance saves NEVER imply new capital or EXPLICIT_RECONFIGURE.
   if(reason){
    const previousTarget=model.target?.target_id??null;
    pendingTargetRequest={reason,expected_revision:savedRevision,previous_target_id:previousTarget};
    await finishTargetRequest(token);
   }
   return requestDaily(token);
  },input);}
 };
}
function fetchTransport(fetchImpl,{timeoutMs=180000}={}){
 if(!Number.isFinite(timeoutMs)||timeoutMs<=0)throw new Error('INVALID_REQUEST_TIMEOUT');
 return async(path,body)=>{
  const abort=new AbortController();
  let timer;
  const deadline=new Promise((_,reject)=>{
   timer=setTimeout(()=>{
    const error=new Error('DAILY_REQUEST_TIMEOUT');
    // An aborted connection does not prove that a server-side write stopped.
    if(body!==undefined&&path!=='/api/strategy-daily-v3/preview'){
     error.write_may_have_occurred=true;error.reconcile_before_retry=true;
    }
    reject(error);abort.abort();
   },timeoutMs);
  });
  const operation=async()=>{
  const response=await fetchImpl(path,body===undefined?{cache:'no-store',signal:abort.signal}:
   {method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let value;
  try{value=await response.json();}catch(error){throw new Error('DAILY_RESPONSE_UNAVAILABLE');}
  if(value===null||typeof value!=='object'||Array.isArray(value))throw new Error('DAILY_RESPONSE_UNAVAILABLE');
  if(!response.ok||value.status==='BLOCKED'||value.write_may_have_occurred||value.reconcile_before_retry){
   const error=new Error(value.reason||'REQUEST_NOT_CONFIRMED');
   error.responseStatus=response.status;error.responseBody=value;
   throw error;
  }
  return value;
  };
  // Cover response-body stalls too, even if a transport ignores abort.
  try{return await Promise.race([operation(),deadline]);}
  finally{clearTimeout(timer);}
 };
}

function httpDependencies(request,eventId,accountController){
 // request(path, body?) handles existing app transport/errors. Server owns
 // policy/release configuration; no policy or approval fields are sent.
 let generationAttempt=null;
 return {
  loadAccount:async()=> (await request('/api/strategy-account')).account,
  loadTarget:()=>request('/api/strategy-account/target'),
  saveCash:({amount,expected_revision})=>{
   if(!accountController?.confirmCash)fail('ACCOUNT_CONTROLLER_REQUIRED');
   if(accountController.getState().account?.revision!==expected_revision)fail('ACCOUNT_CONTROLLER_RELOAD_REQUIRED');
   return accountController.confirmCash({amount}).then(value=>value.account);
  },
  generateTarget:body=>{
   const key=JSON.stringify(body);
   if(generationAttempt&&generationAttempt.key!==key){
    if(!generationAttempt.result)fail('TARGET_WRITE_RECONCILIATION_REQUIRED');
    generationAttempt=null;
   }
   if(generationAttempt?.result)return Promise.resolve(copy(generationAttempt.result));
   if(!generationAttempt)generationAttempt={key,event_id:eventId()};
   return request('/api/strategy-account/target/generate',{...body,event_id:generationAttempt.event_id})
    .then(value=>{
     if(!value?.target_id)fail('TARGET_GENERATION_REQUIRED');
     generationAttempt.result=copy(value);return value;
    }).catch(error=>{
     // Only a structured response from this endpoint's pre-publication checks
     // proves no operation exists. Network errors or arbitrary messages cannot.
     const response=error.responseBody;
     const definite=error.responseStatus===409&&response?.status==='BLOCKED'&&
      ['STALE_REVISION','STALE_TARGET','ACCOUNT_CHANGED_DURING_TARGET'].includes(response.reason);
     if(definite&&!error.write_may_have_occurred&&!error.reconcile_before_retry&&
        !response.write_may_have_occurred&&!response.reconcile_before_retry){
      generationAttempt=null;error.target_not_committed=true;
     }
     throw error;
    });
  },
  previewDaily:body=>request('/api/strategy-daily-v3/preview',body)
 };
}
function presentation(model,now=Date.now()){
 const daily=model.daily;
 const bound=daily&&daily.account_revision===model.account?.revision&&daily.target_id===model.target?.target_id;
 const ready=bound&&['READY','CONDITIONAL_PREVIEW_READY'].includes(daily.status)&&!model.busy&&!model.error;
 const orders=ready?(daily.new_orders||[]):[];
 const quotes=ready?(daily.reference_quotes||{}):{};
 const rows=new Map();
 const add=sid=>{if(!rows.has(sid))rows.set(sid,{security_id:sid,held:0,monthly_target:null,daily_effective_target:null,action:'WAIT',orders:[],historical_orders:[],quotes:null,historical_quote:null});return rows.get(sid);};
 for(const row of model.account?.holdings||[])Object.assign(add(row.security_id),{held:row.quantity,ticker:row.ticker});
 // The saved selector target precedes the cap. Only the bound policy response
 // supplies displayable monthly quantities; missing evidence is not zero.
 for(const row of model.target?.targets||[])Object.assign(add(row.security_id),{ticker:row.ticker});
 const capTargets=bound&&model.account?.revision&&model.target?.target_id&&!model.error&&daily.policy_id==='MONTHLY_CAP50_EXIT20'&&
  daily.risk_monthly_targets&&typeof daily.risk_monthly_targets==='object'&&!Array.isArray(daily.risk_monthly_targets)?daily.risk_monthly_targets:null;
 const monthlyRows=model.target?.targets||[],monthlyIds=new Set(monthlyRows.map(row=>row.security_id));
 const completeMonthly=capTargets&&Array.isArray(model.target?.targets)&&monthlyIds.size===monthlyRows.length&&Object.keys(capTargets).length===monthlyIds.size&&
  Object.entries(capTargets).every(([sid,quantity])=>monthlyIds.has(sid)&&Number.isSafeInteger(quantity)&&quantity>=0);
 if(capTargets){
  for(const [sid,quantity] of Object.entries(capTargets)){
   if(Number.isSafeInteger(quantity)&&quantity>=0)add(sid).monthly_target=quantity;
  }
 }
 for(const row of bound?daily.daily_gate?.rows||[]:[]){
  const target=add(row.security_id);
  target.action=ready||(daily.status==='HOLD'&&!model.busy&&!model.error)?row.action:'WAIT';target.reason=row.reason;
  target.daily_effective_target=daily.effective_target_quantities?.[row.security_id]??row.effective_target??null;
 }
 for(const [sid,quote] of Object.entries(model.historicalQuotes||{}))add(sid).historical_quote={...copy(quote),label:'历史参考，不是当前建议',executable:false};
 for(const [sid,saved] of Object.entries(model.historicalOrders||{})){
  add(sid).historical_orders=saved.map(order=>({...copy(order),executable:false,label:'上一条建议 · 已失效，待刷新'}));
 }
 for(const [sid,quote] of Object.entries(quotes)){
  if(!(daily.daily_gate?.rows||[]).some(row=>row.security_id===sid&&['BUY','SELL'].includes(row.action)))continue;
  const row=add(sid),deadline=Date.parse(quote.reference_valid_until);
  if(row.action!=='WAIT'&&Number.isFinite(deadline)&&deadline>now)row.quotes=copy(quote);
  else row.historical_quote={...copy(quote),label:'历史参考，不是当前建议',executable:false};
 }
 const currentOrders=(daily?.new_orders||[]).filter(order=>
  ['READY','CONDITIONAL_PREVIEW_READY'].includes(daily.status)&&(daily.daily_gate?.rows||[]).some(row=>
   row.security_id===order.security_id&&row.action===order.side&&['BUY','SELL'].includes(row.action)));
 for(const sid of new Set(currentOrders.map(order=>order.security_id)))add(sid).historical_orders=[];
 for(const order of currentOrders){
  const row=add(order.security_id);
  const sourceDeadline=Date.parse(daily.reference_quotes?.[order.security_id]?.reference_valid_until);
  const deadline=Math.min(sourceDeadline,Date.parse(order.reference_valid_until||daily.reference_quotes?.[order.security_id]?.reference_valid_until));
  if(ready&&row.action!=='WAIT'&&Number.isFinite(deadline)&&deadline>now)row.orders.push(copy(order));
  else row.historical_orders.push({...copy(order),executable:false,label:'上一条建议 · 已失效，待刷新'});
 }
 for(const row of rows.values()){
  // A complete policy map establishes zero for old holdings outside its domain.
  if(completeMonthly&&!monthlyIds.has(row.security_id))row.monthly_target=0;
  if(!row.ticker){
   const fill=[...(model.account?.fills||[])].reverse().find(item=>item.security_id===row.security_id&&item.ticker);
   if(fill)row.ticker=fill.ticker;
  }
  if((row.action==='BUY'||row.action==='SELL')&&!row.orders.length)row.action='WAIT';
 }
 const expired=ready&&orders.length>0&&![...rows.values()].some(row=>row.orders.length);
 return {status:expired?'WAIT_FRESH_SIGNAL':bound?daily.status:'WAIT_SIGNAL',detail_status:expired?'WAIT_FRESH_SIGNAL':bound?daily.detail_status:null,reason:expired?null:bound?daily.reason:null,error:model.error,cashSaved:model.cashSaved,rows:[...rows.values()],
         monthly_target_label:'本月目标',daily_target_label:'今日有效目标'};
}
function dollars(value){
 const parts=String(value??'').split('/');
 if(parts.length>2||parts.some(x=>!x.trim()))return '—';
 const number=Number(parts[0])/(parts.length===2?Number(parts[1]):1);
 return Number.isFinite(number)?'$'+number.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
}
function actionExplanation(row,result,model){
 if(!row.orders.length){
  if(result.error)return waitingExplanation(result.error)||'本次刷新失败，旧建议不可用于挂单。';
  const waitingData=(model.daily?.waiting_data||[]).find(item=>item.security_id===row.security_id);
  if(waitingData){
   const reason=waitingData.data_failure||model.daily?.buy_data_failure;
   if(reason==='HALT_ACTIVE_OR_RESUME_UNCONFIRMED')return '停牌或尚未确认复牌，暂不生成买入限价。';
   if(reason==='POST_RESUMPTION_COMPLETE_BAR_REQUIRED')return '已复牌，等待复牌后的完整成交分钟，再判断买入。';
   if(reason==='HALT_EXECUTION_EVIDENCE_REQUIRED'||reason==='HALT_SOURCE_CLOCK_OR_STALE')return '停复牌信息暂未核验，买入等待；有效卖出单单独显示。';
   return '分钟行情缺失或不完整，买入暂缓；有效卖出单单独显示。';
  }
  if(row.action==='HOLD'){
   const note=model.daily?.signal_explanations?.[row.security_id];
   if(note?.policy==='MONTHLY_CAP50_EXIT20'&&note.exited===true&&
      /^\d{4}-\d{2}-\d{2}$/.test(note.signal_date)&&note.monthly_target===row.monthly_target&&
      note.effective_target===0&&row.daily_effective_target===0&&row.held===0)
    return note.signal_date+' 收盘已触发月内峰值回落20%退出；当前保持空仓，本月不再买入。';
   return row.held===0&&row.daily_effective_target===0?'当前空仓，今日无需买卖。':'已符合今日持仓目标，无需买卖。';
  }
  const pending=model.daily?.difference?.binding?.pending_orders||[];
  if(row.reason==='PENDING_RECONCILIATION_REQUIRED'||pending.some(order=>order.security_id===row.security_id))return '已有未成交挂单，等待成交或撤单后更新。';
  if(row.reason==='NO_AVAILABLE_CASH'||[...(model.daily?.waiting_cash||[]),...(model.daily?.difference?.waiting_cash||[])].some(item=>item.security_id===row.security_id))return '可用现金不足，等待资金到账后更新；未成交卖款不计入可用现金。';
  if(row.historical_orders.length)return '上一条建议已失效，更新现金后重新判断。';
  return waitingExplanation(result.error||result.reason)||({DAILY_PACKET_NEEDS_RECOVERY:'今日数据核验异常，暂不建议操作。',WAIT_NEXT_SESSION:'交易时段已结束，等待下一交易日。',WAIT_MONTHLY_TARGET:'等待本月目标配置。'})[result.reason]||'等待有效数据和报价，暂不建议操作。';
 }
 const target=row.daily_effective_target,monthly=row.monthly_target;
 const reduced=target!==null&&monthly!==null&&target<monthly;
 const note=model.daily?.signal_explanations?.[row.security_id];
 const verifiedNote=note?.policy==='SMA20_HALF_OFF_RESEARCH'&&
  /^\d{4}-\d{2}-\d{2}$/.test(note.signal_date)&&typeof note.above_sma20==='boolean'&&
  note.monthly_target===monthly&&note.effective_target===target;
 const peakNote=note?.policy==='MONTHLY_CAP50_EXIT20'&&
  /^\d{4}-\d{2}-\d{2}$/.test(note.signal_date)&&typeof note.exited==='boolean'&&
  note.monthly_target===monthly&&note.effective_target===target;
 const basis=peakNote?(note.signal_date+' 收盘判断；'+(note.exited?
  '已触发月内峰值回落20%退出，本月不再买入。':'未触发退出，按单股50%配置上限后的目标调整。')):verifiedNote?(note.signal_date+' 收盘'+(note.above_sma20?'高于':'不高于')+
  '20日均线；'+(note.above_sma20?'沿用本月目标。':'本月目标减半并向下取整。')):'';
 const prefix=basis+(reduced?'风控将目标从 '+monthly+' 股降至 '+target+' 股；':'今日目标 '+target+' 股；');
 return row.orders.map(order=>{
  if(order.side==='SELL')return prefix+'现持 '+row.held+' 股，减仓 '+order.quantity+' 股。';
  const shortage=(model.daily?.difference?.waiting_cash||[]).find(item=>item.security_id===row.security_id);
  return prefix+'现持 '+row.held+' 股，'+(shortage?'按可用现金先买 '+order.quantity+' 股，余 '+shortage.quantity+' 股待资金。':'补入 '+order.quantity+' 股。');
 }).join(' ');
}
function render(container,model,now=Date.now()){
 const result=presentation(model,now),doc=container.ownerDocument;
 const table=doc.createElement('table'),head=doc.createElement('tr');table.className='daily-actions-table';
 for(const text of ['股票','实际持有',result.monthly_target_label,result.daily_target_label,'今日动作','建议限价','原因']){
  const cell=doc.createElement('th');cell.textContent=text;head.appendChild(cell);
 }
 table.appendChild(head);
 for(const row of result.rows){
  const tr=doc.createElement('tr');
  const prices=row.orders.map(order=>dollars(order.limit_price)).join('；');
  const action=row.orders.map(order=>(order.side==='SELL'?'卖出':'买入')+' '+order.quantity+' 股').join('；');
  const history=row.historical_quote;
  const savedOrders=row.historical_orders.map(order=>(order.side==='SELL'?'卖出':'买入')+' '+order.quantity+' 股 · '+dollars(order.limit_price)).join('；');
  const savedQuotes=history?[
   ['买入',history.buy_limit??history.buy],['卖出',history.sell_limit??history.sell]
  ].filter(([,value])=>value!==undefined&&value!==null).map(([side,value])=>side+' '+dollars(value)).join('；'):'';
  const waitingData=(model.daily?.waiting_data||[]).some(item=>item.security_id===row.security_id);
  const historical=waitingData?'暂无有效买入限价':savedOrders||savedQuotes?'上一条建议（已失效，待刷新）：'+(savedOrders||savedQuotes):'';
  const cells=[row.ticker||row.security_id,row.held,row.monthly_target??'待核验',row.daily_effective_target??'—',
   action||({BUY:'条件买入',SELL:'条件卖出',HOLD:row.held===0?'空仓，无需操作':'持有，无需操作',WAIT:'等待'})[row.action]||'等待',prices||historical||'暂无有效建议',actionExplanation(row,result,model)];
  for(const [index,text] of cells.entries()){
   const td=doc.createElement('td');td.textContent=String(text);
   if(index===5&&!prices&&historical){td.className='historical-advice';if(td.style){td.style.fontSize='0.9em';td.style.fontWeight='400';td.style.color='#64748b';}}
   tr.appendChild(td);
  }
  table.appendChild(tr);
 }
 const explanations={
  APPROVED_SERVER_RELEASE_NOT_CONFIGURED:'等待策略正式启用',
  WAIT_NEW_SESSION_EVIDENCE:'等待今日数据核验',
  WAIT_NEW_SECURITY_EVIDENCE:'等待新股票数据核验',
  WAIT_POLICY_REVIEW_AUTHORIZATION:'等待策略审核配置完成',
  WAIT_PREVIOUS_SESSION_EVIDENCE:'缺少前一交易日数据，暂不生成买卖建议',
  INCOMPLETE_DAILY_PACKET:'今日数据尚未完整，暂不生成买卖建议',
  DAILY_PACKET_NEEDS_RECOVERY:'今日数据核验异常，暂不生成买卖建议',
  WAIT_COMPLETE_SECURITY_DOMAIN:'等待持仓及目标股票的数据全部核验',
  WAIT_NEXT_SESSION:'今日交易时段已结束，等待下一交易日',
  HOLD:'持有，今日无需操作',WAIT_POLICY_RELEASE:'等待策略启用',WAIT_SIGNAL:'等待有效信号',
  WAIT_FRESH_SIGNAL:'等待最新信号',WAIT_MONTHLY_TARGET:'等待本月目标',
  DAILY_PREVIEW_DISABLED:'每日信号暂未启用',READY:'今日条件买卖建议',WAIT:'等待有效执行条件',CONDITIONAL_PREVIEW_READY:'今日条件买卖建议'
 };
 const status=doc.createElement('p');status.textContent=waitingExplanation(result.error||result.reason)|| (result.error?(result.cashSaved?'现金已保存；建议未更新，请刷新，无需重复保存现金':'状态未确认，请刷新核对后再操作'):
  explanations[result.reason]||explanations[result.detail_status]||explanations[result.status]||'等待执行条件满足');
 container.replaceChildren(status,table);return result;
}
const api={waitingExplanation,createController,httpDependencies,fetchTransport,presentation,render,dollars,actionExplanation};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyDailyController=api;
})(typeof window!=='undefined'?window:globalThis);
