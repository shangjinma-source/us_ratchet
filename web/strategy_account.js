(function(root){
'use strict';
// Isolated component: importing it does not create accounts or mount production UI.
const API='/api/strategy-account';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const errors={STALE_REVISION:'记录已变化，请刷新账户后重新核对。',EVENT_ID_CONFLICT:'这笔记录的编号发生冲突，请核对，勿重复录入。',LINK_FILL_TO_EXISTING_ORDER:'此股票有未结订单，请选择对应订单记录成交。',CASH_RECONFIRMATION_REQUIRED:'请先确认成交后的最新可用现金。',INSUFFICIENT_STRATEGY_SHARES:'卖出股数超过新策略实际持股，旧持仓不参与。',INVALID_FILL_QUANTITY:'成交股数超过关联订单的剩余股数。',BUSY:'正在保存，请勿重复提交。',UNKNOWN_TICKER:'未能核验此股票，请检查代码。'};
function issue(code){const e=Error(code);e.code=code;if(code==='RECONCILE_REQUIRED'){e.reconcile_before_retry=true;e.write_may_have_occurred=true;}return e;}
errors.ACCOUNT_REQUEST_TIMEOUT='账户读取超时，请重新刷新账户。';
errors.RECONCILE_REQUIRED='这笔操作可能已经保存。请先刷新账户核对记录，勿重复录入。';
function amount(value){let text=String(value).trim();if(/^[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?$/.test(text))text=text.replace(/,/g,'');if(!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(text))throw issue('请输入非负金额。');return text;}
function shares(value){const n=Number(value);if(!Number.isSafeInteger(n)||n<=0)throw issue('请输入正整数股数。');return n;}
function beijingTime(value){
 const text=String(value).trim();if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(text))throw issue('请填写北京时间，精确到分钟或秒。');
 const full=text.length===16?text+':00':text;const date=new Date(full+'+08:00');
 if(!Number.isFinite(date.getTime())||new Date(date.getTime()+8*3600000).toISOString().slice(0,19)!==full)throw issue('成交日期或时间无效。');
 return full+'+08:00';
}
function displayTime(value){
 if(typeof value!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/.test(value)||!Number.isFinite(Date.parse(value)))return '时间待核验';
 return new Date(Date.parse(value)+8*3600000).toISOString().slice(0,19).replace('T',' ');
}
function display(value){
 const text=String(value??'');const p=text.split('/');const n=Number(p[0])/(p.length===2?Number(p[1]):1);
 return p.length<=2&&Number.isFinite(n)?n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'待核验';
}
function validate(data){
 if(data?.status==='NOT_INITIALIZED')return null;
 const a=data?.account;if(data?.status!=='READY'||!a||typeof a.revision!=='string'||!a.revision||!Array.isArray(a.holdings)||!Array.isArray(a.orders)||typeof a.cash_confirmation_valid!=='boolean')throw issue('账户响应不完整，请刷新重试。');
 return a;
}
function render(model){
 let html='<section class="strategy-account"><div class="account-header"><h3>实际账户</h3><button type="button" data-action="refresh" '+(model.busy?'disabled':'')+'>刷新账户</button><button type="button" data-action="valuation" '+(model.busy||model.valuationLoading?'disabled':'')+'>'+(model.valuationLoading?'市值更新中…':'更新市值')+'</button></div>';
 if(model.message)html+='<p role="status">'+esc(model.message)+'</p>';
 if(model.busy)html+='<p aria-live="polite">正在读取或保存…</p>';
 if(!model.loaded)return html+'</section>';
 if(!model.account)return html+'<p>仅记录新策略的真实持股。旧持仓由你自行处理，不会导入；不会向券商下单。</p><button type="button" data-action="enable" '+(model.busy?'disabled':'')+'>启用实际账户</button></section>';
 const a=model.account,disabled=model.busy?'disabled':'';
 const value=model.valuation?.account_revision===a.revision?model.valuation:null;
 const number=v=>{const p=String(v).split('/');return Number(p[0])/(p.length===2?Number(p[1]):1);};
 const costRows=a.holding_costs||[];
 const costsComplete=a.holdings.every(h=>costRows.some(row=>row.security_id===h.security_id&&Number.isFinite(number(row.total_cost))));
 const cost=costsComplete?costRows.reduce((sum,row)=>sum+number(row.total_cost),0):null;
 const cash=a.cash_confirmation_valid?number(a.total_uninvested_cash??a.cash):null;
 const total=value?.strategy_total!=null?value.strategy_total:cash!==null&&cost!==null?cash+cost:null;
 html+='<div class="preview-metrics"><div>'+(value?'持仓市值':'持仓金额（成本口径）')+'<strong>'+esc(value?'$'+display(value.market_value):cost!==null?'$'+display(cost):'成本待补充')+'</strong></div><div>持仓成本<strong>'+esc(cost!==null?'$'+display(cost):'待补充')+'</strong></div><div>可用现金<strong>'+esc(a.cash_confirmation_valid?'$'+display(a.available_cash??a.cash):'请在今日建议填写')+'</strong></div><div>'+(value?'账户总额':'账户总额（成本口径）')+'<strong>'+esc(cash===null?'请在今日建议填写':total!==null?'$'+display(total):'成本待补充')+'</strong></div></div>';
 if(value)html+='<details><summary>估值明细</summary><p class="preview-caption">读取于 '+esc(value.valued_at)+'；价格会变化，公开行动核查可能漏报。'+value.holdings.map(row=>esc(row.ticker)+' $'+esc(display(row.price))+'（'+esc(row.observed_at)+'）').join(' · ')+'</p></details>';
 const costs=Object.fromEntries((a.holding_costs||[]).map(row=>[row.security_id,row]));
 html+='<div style="overflow-x:auto"><table><thead><tr><th>股票</th><th>实际股数</th><th>持仓均价 USD</th><th>持仓成本 USD</th></tr></thead><tbody>';
 for(const h of a.holdings){const cost=costs[h.security_id];html+='<tr><td>'+esc(h.ticker)+'</td><td>'+esc(h.quantity)+'</td><td>'+esc(cost?display(cost.average_cost):'待核验')+'</td><td>'+esc(cost?display(cost.total_cost):'待核验')+'</td></tr>';}
 html+='</tbody></table></div>'+(a.holdings.length?'':'<p>尚无新策略持仓。</p>');
 

 const choices=[...new Set([...(model.recommendedTickers||[]),...a.holdings.map(h=>h.ticker)])];
 const defaultTicker=choices[0]||'';
 html+='<section class="account-trades"><h4>成交记录</h4>';
 if(model.pendingFill)html+='<p>上次成交尚未确认，暂不接受新的录入。</p><button type="button" data-action="recover-fill" '+disabled+'>继续核对并保存上次成交</button>';
 else html+='<form data-form="fill"><label>股票 <input name="ticker" list="strategy-fill-tickers" value="'+esc(defaultTicker)+'" placeholder="输入股票代码" required autocomplete="off"><datalist id="strategy-fill-tickers">'+choices.map(ticker=>'<option value="'+esc(ticker)+'">'+((model.recommendedTickers||[]).includes(ticker)?'今日推荐':'已有持仓')+'</option>').join('')+'</datalist></label> <label>方向 <select name="side"><option value="BUY">买入</option><option value="SELL">卖出</option></select></label> <label>股数 <input name="quantity" type="number" min="1" step="1" required></label> <label>成交价 USD <input name="price" inputmode="decimal" required></label> <label>成交时间（北京时间）<input name="executed_at" type="datetime-local" step="1" required></label> <button '+disabled+'>保存真实成交</button></form>';
 if(a.fills?.length){html+='<details><summary>已录真实成交 · '+esc(a.fills.length)+' 笔</summary><table><thead><tr><th>成交时间（北京时间）</th><th>股票</th><th>方向</th><th>股数</th><th>成交价 USD</th></tr></thead><tbody>';for(const f of [...a.fills].reverse())html+='<tr><td>'+esc(displayTime(f.executed_at))+'</td><td>'+esc(f.ticker)+'</td><td>'+(f.side==='BUY'?'买入':'卖出')+'</td><td>'+esc(f.quantity)+'</td><td>'+esc(display(f.price))+'</td></tr>';html+='</tbody></table></details>';}
 html+='</section>';

 if(a.orders.length){html+='<details><summary>未结订单</summary>';for(const o of a.orders)html+='<p>'+esc(o.ticker)+' · '+(o.side==='BUY'?'买入':'卖出')+' '+esc(o.remaining_quantity)+' 股 <button type="button" data-action="cancel" data-order="'+esc(o.order_id)+'" '+disabled+'>已在券商撤单，记录撤销</button></p>';html+='</details>';}
 return html+'</section>';
}
function browserPendingFillStore(storage,key){
 return {
  read(){const raw=storage.getItem(key);if(raw===null)return null;
   if(raw.length>16384)throw issue('成交待核对记录异常，请先核对账户。');
   const value=JSON.parse(raw);
   if(!value||Object.keys(value).sort().join()!=='eventId,key'||typeof value.eventId!=='string'||!value.eventId||value.eventId.length>128||typeof value.key!=='string'||!value.key)
    throw issue('成交待核对记录异常，请先核对账户。');
   return value;
  },
  write(value){const existing=this.read();if(existing&&existing.eventId!==value.eventId)throw issue('RECONCILE_REQUIRED');storage.setItem(key,JSON.stringify(value));},
  clear(eventId){if(this.read()?.eventId===eventId)storage.removeItem(key);}
 };
}
function createController({fetchImpl=root.fetch,onRender=()=>{},onInvalidate=()=>{},makeId=()=>root.crypto.randomUUID(),automaticValuationEnabled=true,requestTimeoutMs=180000,pendingFillStore=null}={}){
 if(!Number.isFinite(requestTimeoutMs)||requestTimeoutMs<=0)throw issue('INVALID_REQUEST_TIMEOUT');
 let model={loaded:false,account:null,busy:false,message:''},generation=0,retry=null,recommendedTickers=[],reconciliation=pendingFillStore?.read()||null,valuationPromise=null;
 if(reconciliation)retry={...reconciliation};
 const snapshot=()=>structuredClone({...model,recommendedTickers});
 const emit=()=>onRender(render({...model,recommendedTickers}),snapshot());
 function invalidate(){model.valuation=null;onInvalidate();}
 async function request(path,body){
  const abort=new AbortController();let timer;
  const deadline=new Promise((_,reject)=>{
   timer=setTimeout(()=>{
    // The server may still commit after the connection is interrupted.
    reject(issue(body===undefined?'ACCOUNT_REQUEST_TIMEOUT':'RECONCILE_REQUIRED'));
    abort.abort();
   },requestTimeoutMs);
  });
  const operation=async()=>{
  let response;
  try{response=await fetchImpl(API+path,body===undefined?{cache:'no-store',signal:abort.signal}:{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
  catch(error){if(body!==undefined)throw issue('RECONCILE_REQUIRED');throw error;}
  let data;
  try{data=await response.json();}catch(error){throw issue(body!==undefined?'RECONCILE_REQUIRED':'服务返回异常，请刷新核对账户后再操作。');}
  if(body!==undefined&&(!data||typeof data!=='object'||response.status>=500))throw issue('RECONCILE_REQUIRED');
  if(data.reconcile_before_retry===true||data.write_may_have_occurred===true)throw issue('RECONCILE_REQUIRED');if(!response.ok||data.status==='BLOCKED')throw issue(data.reason||'保存未确认，请刷新核对后再试。');return data;
  };
  try{return await Promise.race([operation(),deadline]);}
  finally{clearTimeout(timer);}
 }

 async function load(){
  if(model.busy)return;
  const version=++generation;model.busy=true;model.message='';emit();
  try{
   const saved=pendingFillStore?.read();if(saved){reconciliation=saved;retry={...saved};}
   const account=validate(await request(''));if(version!==generation)return;
   if(model.account?.revision!==account?.revision)invalidate();
   const recorded=reconciliation&&account?.fills?.some(fill=>fill.fill_id===reconciliation.eventId);
   const pendingFill=!!saved&&!recorded&&account?.revision===JSON.parse(saved.key).expected;
   // A missing fill on the original revision may still be in flight. Only a
   // recorded fill or a changed CAS revision resolves this persisted request.
   if(saved&&!pendingFill)pendingFillStore.clear(saved.eventId);
   model={loaded:true,account,busy:false,pendingFill,message:reconciliation?(recorded?'已核对：刚才的成交已经记录，请勿重复录入。':pendingFill?'上次成交结果仍待确认；请继续核对原记录，勿重新录入。':'账户已刷新，请核对刚才的记录后再操作。'):''};reconciliation=null;
  }
  catch(e){if(version!==generation)return;invalidate();model={loaded:false,account:null,busy:false,message:errors[e.code]||e.message};}
  finally{if(version===generation){model.busy=false;emit();}}
 }
 async function mutate(path,fields){
  if(model.busy)throw issue('BUSY');
  if(reconciliation)throw issue('RECONCILE_REQUIRED');
  const expected=model.account?.revision;const key=JSON.stringify({path,fields,expected});
  const saved=pendingFillStore?.read();
  if(saved&&saved.key!==key)throw issue('RECONCILE_REQUIRED');
  const eventId=saved?.eventId||(retry?.key===key?retry.eventId:makeId());retry={key,eventId};
  const body=path==='/initialize'?{event_id:eventId}:{expected_revision:expected,event:{event_id:eventId,...fields}};
  const persistedFill=['DIRECT_FILL','FILL'].includes(fields.kind)&&pendingFillStore;
  // Persist before sending: closing the page must not forget an uncertain fill.
  if(persistedFill)pendingFillStore.write({eventId,key});
  const version=++generation;model.busy=true;model.message='';invalidate();emit();
  try{const data=await request(path,body);if(version!==generation)return;let account;try{account=validate(data);if(!account)throw issue('账户保存结果缺失。');if(persistedFill)pendingFillStore.clear(eventId);}catch(_){throw issue('RECONCILE_REQUIRED');}model={loaded:true,account,busy:false,message:fields.kind?.includes('FILL')?'成交已记录。':'记录已保存，旧建议已撤下。'};retry=null;emit();await automaticValuation();return data;}
  catch(e){if(version===generation){model.message=errors[e.code]||e.message;if(e.code==='RECONCILE_REQUIRED'){reconciliation={eventId};model.loaded=false;model.account=null;}else if(e.code==='STALE_REVISION'||e.code==='EVENT_ID_CONFLICT'){model.loaded=false;model.account=null;retry=null;}}throw e;}
  finally{if(version===generation){model.busy=false;emit();}}
 }
 const requireAccount=()=>{if(reconciliation||model.pendingFill)throw issue('RECONCILE_REQUIRED');if(!model.loaded||!model.account)throw issue('请先启用并读取新策略账户。');};
 async function automaticValuation(){
  if(!automaticValuationEnabled)return;
  try{await valuation(true);}catch(_){/* Valuation failure must never turn a successful save into a failed save. */}
 }
 function valuation(quiet=false){
  if(valuationPromise)return valuationPromise;
  valuationPromise=performValuation(quiet).finally(()=>{valuationPromise=null;});
  return valuationPromise;
 }
 async function performValuation(quiet=false){
  requireAccount();if(model.busy||model.valuationLoading)throw issue('BUSY');
  const revision=model.account.revision,version=generation;model.valuationLoading=true;if(!quiet)model.message='正在读取持仓估值…';emit();
  try{const data=await request('/valuation');if(version!==generation)return;
   if(data.account_revision!==revision||model.account?.revision!==revision||!Array.isArray(data.holdings))throw issue('STALE_REVISION');
   const waiting={EMPTY_HOLDINGS:'当前没有持仓，无需更新市值。',WAIT_SAVED_TARGET:'等待已保存策略目标，暂按成本显示。',WAIT_REGULAR_SESSION:'美股常规交易时段可更新市值，暂按成本显示。'};
   if(Object.hasOwn(waiting,data.status)){model.valuation=null;model.message=waiting[data.status];return;}
   if(data.status!=='READY')throw issue('估值响应不完整。');
   model.valuation=data;if(!quiet)model.message='估值已更新。';
  }catch(e){if(version===generation){model.valuation=null;model.message=quiet?'市值暂不可用，当前按成本显示。':errors[e.code]||e.message;}throw e;}
  finally{if(version===generation){model.valuationLoading=false;emit();}}
 }
 return {
  load,valuation,refresh:async()=>{if(model.busy)return;const reconciling=Boolean(reconciliation);await load();if(!reconciling&&model.loaded&&model.account)await automaticValuation();},getState:snapshot,
  recoverFill:async()=>{
   if(model.busy)throw issue('BUSY');
   await load();
   if(!model.loaded||!model.account)throw issue('RECONCILE_REQUIRED');
   const saved=pendingFillStore?.read();if(!saved)return;
   const original=JSON.parse(saved.key);
   if(original.path!=='/events'||!['DIRECT_FILL','FILL'].includes(original.fields?.kind)||original.expected!==model.account.revision)throw issue('RECONCILE_REQUIRED');
   return mutate(original.path,original.fields);
  },
  setRecommendedTickers:tickers=>{const next=[...new Set((Array.isArray(tickers)?tickers:[]).map(t=>String(t).trim().toUpperCase()).filter(t=>/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(t)))];if(JSON.stringify(next)===JSON.stringify(recommendedTickers))return;recommendedTickers=next;emit();},
  initialize:()=>{if(!model.loaded||model.account)throw issue('请先读取账户状态。');return mutate('/initialize',{});},
  confirmCash:({amount:value})=>{requireAccount();return mutate('/events',{kind:'CASH_CONFIRM',amount:amount(value),cash_basis:'AVAILABLE_AFTER_RESERVATIONS'});},
  recordOrder:input=>{
   requireAccount();const ticker=String(input.ticker).trim().toUpperCase(),side=input.side,order_id=String(input.order_id).trim();
   if(!order_id||!/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(ticker)||!['BUY','SELL'].includes(side))throw issue('请检查订单编号、股票和方向。');
   const limit_price=amount(input.limit_price);if(Number(limit_price)<=0)throw issue('限价必须大于零。');
   return mutate('/events',{kind:'ORDER_OPEN',order_id,ticker,side,quantity:shares(input.quantity),limit_price,fee_per_share:amount(input.fee_per_share)});
  },
  recordFill:input=>{
   requireAccount();const ticker=String(input.ticker).trim().toUpperCase(),side=input.side;if(!/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(ticker)||!['BUY','SELL'].includes(side))throw issue('请检查股票与买卖方向。');
   const event={quantity:shares(input.quantity),price:amount(input.price),fees:amount(input.fees??0),executed_at:beijingTime(input.executed_at)};if(Number(event.price)<=0)throw issue('成交价必须大于零。');
   const pending=model.account.orders.filter(o=>o.ticker===ticker),matching=pending.filter(o=>o.side===side);let orderId=String(input.order_id||'');
   if(!orderId&&matching.length>1)throw issue('此股票有多笔同方向未结订单，无法自动判断成交归属。请先核对订单编号，通过明确订单关联录入，或在券商撤单后记录撤销。');
   if(!orderId&&matching.length===1)orderId=matching[0].order_id;
   if(orderId){const order=model.account.orders.find(o=>o.order_id===orderId);if(!order||order.ticker!==ticker||order.side!==side)throw issue('关联订单与股票或方向不一致。');if(event.quantity>order.remaining_quantity)throw issue('INVALID_FILL_QUANTITY');return mutate('/events',{kind:'FILL',order_id:orderId,...event});}
   if(pending.length)throw issue('此股票存在相反方向未结订单，请先核对成交方向与订单状态。');return mutate('/events',{kind:'DIRECT_FILL',ticker,side,...event});
  },
  cancel:order_id=>{requireAccount();if(!model.account.orders.some(o=>o.order_id===order_id))throw issue('未找到未结订单，请刷新。');return mutate('/events',{kind:'CANCEL',order_id});},
  dispose:()=>{generation++;model.loaded=false;model.account=null;}
 };
}
function mount({container,initialValuation=true,...options}){
 let previousDefaultTicker='';
 const controller=createController({...options,onRender:(html,state)=>{
  const drafts=Array.from(container.querySelectorAll('form[data-form]')).map(form=>({kind:form.dataset.form,fields:Object.fromEntries(new FormData(form))}));
  container.innerHTML=html;
  if(state.busy||!['成交已记录。','记录已保存，'].some(prefix=>state.message.startsWith(prefix))){
   for(const draft of drafts){const form=container.querySelector(`form[data-form="${draft.kind}"]`);if(form)for(const [name,value] of Object.entries(draft.fields)){const input=form.elements.namedItem(name);if(input&&!(draft.kind==='fill'&&name==='ticker'&&(!value||value===previousDefaultTicker)))input.value=value;}}
  }
  previousDefaultTicker=state.recommendedTickers?.[0]||state.account?.holdings?.[0]?.ticker||'';
  options.onRender?.(html,state);
 }});
 const show=e=>{const status=container.querySelector('[role="status"]');if(status)status.textContent=errors[e.code]||e.message;else{const p=document.createElement('p');p.setAttribute('role','status');p.textContent=errors[e.code]||e.message;container.prepend(p);}};
 container.addEventListener('submit',async e=>{const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();const data=Object.fromEntries(new FormData(form));try{await(form.dataset.form==='cash'?controller.confirmCash(data):form.dataset.form==='order'?controller.recordOrder(data):controller.recordFill(data));}catch(error){show(error);}});
 container.addEventListener('click',async e=>{const button=e.target.closest('button[data-action]');if(!button)return;try{if(button.dataset.action==='refresh')await controller.load();else if(button.dataset.action==='recover-fill')await controller.recoverFill();else if(button.dataset.action==='valuation')await controller.valuation();else if(button.dataset.action==='enable')await controller.initialize();else if(button.dataset.action==='cancel')await controller.cancel(button.dataset.order);}catch(error){show(error);}});
 controller.ready=initialValuation?controller.refresh():controller.load();return controller;
}
root.StrategyAccountUI={createController,browserPendingFillStore,render,beijingTime,displayTime,mount};
if(typeof module!=='undefined')module.exports=root.StrategyAccountUI;
})(typeof window!=='undefined'?window:globalThis);
