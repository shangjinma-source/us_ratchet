(function(root){
'use strict';
// Isolated component: importing it does not create accounts or mount production UI.
const API='/api/strategy-account';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const errors={STALE_REVISION:'记录已变化，请刷新账户后重新核对。',EVENT_ID_CONFLICT:'这笔记录的编号发生冲突，请核对，勿重复录入。',LINK_FILL_TO_EXISTING_ORDER:'此股票有未结订单，请选择对应订单记录成交。',CASH_RECONFIRMATION_REQUIRED:'请先确认成交后的最新可用现金。',INSUFFICIENT_STRATEGY_SHARES:'卖出股数超过新策略实际持股，旧持仓不参与。',INVALID_FILL_QUANTITY:'成交股数超过关联订单的剩余股数。',BUSY:'正在保存，请勿重复提交。',UNKNOWN_TICKER:'未能核验此股票，请检查代码。'};
function issue(code){const e=Error(code);e.code=code;if(code==='RECONCILE_REQUIRED'){e.reconcile_before_retry=true;e.write_may_have_occurred=true;}return e;}
errors.ACCOUNT_REQUEST_TIMEOUT='账户读取超时，请重新刷新账户。';
errors.RECONCILE_REQUIRED='这笔操作可能已经保存。请先刷新账户核对记录，勿重复录入。';
errors.ORDER_ALREADY_EXISTS='该券商订单编号已记录，请核对未结订单，勿重复录入。';
function rational(value){const text=String(value);if(/^\d+\/\d+$/.test(text)){const [n,d]=text.split('/').map(BigInt);if(d>0n)return [n,d];}if(/^\d+(?:\.\d+)?$/.test(text)){const [a,b='']=text.split('.');return [BigInt(a+b),10n**BigInt(b.length)];}throw Error('INVALID_AMOUNT');}
function equalAmount(a,b){try{const [an,ad]=rational(a),[bn,bd]=rational(b);return an*bd===bn*ad;}catch(_){return false;}}
function equalReserve(order,intent){try{if(order.side==='SELL')return equalAmount(order.reserved_cash,'0');const [pn,pd]=rational(intent.limit_price),[fn,fd]=rational(intent.fee_per_share);return equalAmount(order.reserved_cash,String((pn*fd+fn*pd)*BigInt(order.remaining_quantity))+'/'+String(pd*fd));}catch(_){return false;}}
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
 const performance=model.performance;
 const performanceFresh=performance?.status==='READY_RECONCILED_NO_EXTERNAL_FLOW'&&performance.account_revision===a.revision&&Number.isFinite(Date.parse(performance.as_of))&&Date.now()-Date.parse(performance.as_of)>=0&&Date.now()-Date.parse(performance.as_of)<=120000;
 html+='<p class="restart-performance">'+(performanceFresh?'本阶段：起始资产 $'+esc(display(performance.initial_equity))+' · 当前资产 $'+esc(display(performance.current_equity))+' · 收益 '+esc(display(number(performance.return_fraction)*100))+'%':'本阶段收益：待核验')+'</p>';
 if(value)html+='<details><summary>估值明细</summary><p class="preview-caption">读取于 '+esc(value.valued_at)+'；价格会变化，公开行动核查可能漏报。'+value.holdings.map(row=>esc(row.ticker)+' $'+esc(display(row.price))+'（'+esc(row.observed_at)+'）').join(' · ')+'</p></details>';
 const costs=Object.fromEntries((a.holding_costs||[]).map(row=>[row.security_id,row]));
 html+='<div style="overflow-x:auto"><table><thead><tr><th>股票</th><th>实际股数</th><th>持仓均价 USD</th><th>持仓成本 USD</th></tr></thead><tbody>';
 for(const h of a.holdings){const cost=costs[h.security_id];html+='<tr><td>'+esc(h.ticker)+'</td><td>'+esc(h.quantity)+'</td><td>'+esc(cost?display(cost.average_cost):'待核验')+'</td><td>'+esc(cost?display(cost.total_cost):'待核验')+'</td></tr>';}
 html+='</tbody></table></div>'+(a.holdings.length?'':'<p>尚无新策略持仓。</p>');
 

 if(a.fills?.length)html+='<h4>成交与盈亏</h4><div data-trade-charts></div>';
 const choices=[...new Set([...(model.recommendedTickers||[]),...a.holdings.map(h=>h.ticker)])];
 const defaultTicker=choices[0]||'';
 html+='<section class="account-trades"><h4>成交记录</h4>';
 if(model.pendingFill)html+='<p>上次操作尚未确认，暂不接受新的录入。</p><button type="button" data-action="recover-fill" '+disabled+'>继续核对上次操作</button>';
 else html+='<form data-form="fill"><label>股票 <input name="ticker" list="strategy-fill-tickers" value="'+esc(defaultTicker)+'" placeholder="输入股票代码" required autocomplete="off"><datalist id="strategy-fill-tickers">'+choices.map(ticker=>'<option value="'+esc(ticker)+'">'+((model.recommendedTickers||[]).includes(ticker)?'今日推荐':'已有持仓')+'</option>').join('')+'</datalist></label> <label>方向 <select name="side"><option value="BUY">买入</option><option value="SELL">卖出</option></select></label> <label>关联委托 <select name="order_id"><option value="">无委托 / 唯一同向委托自动关联</option>'+a.orders.map(o=>'<option value="'+esc(o.order_id)+'">'+esc(o.order_id)+' · '+esc(o.ticker)+' · '+(o.side==='BUY'?'买入':'卖出')+' · 剩余 '+esc(o.remaining_quantity)+' 股</option>').join('')+'</select></label> <label>股数 <input name="quantity" type="number" min="1" step="1" required></label> <label>成交价 USD <input name="price" inputmode="decimal" required></label> <label>成交时间（北京时间）<input name="executed_at" type="datetime-local" step="1" required></label> <button '+disabled+'>保存真实成交</button></form>';
 if(a.fills?.length){html+='<details><summary>已录真实成交 · '+esc(a.fills.length)+' 笔</summary><table><thead><tr><th>成交时间（北京时间）</th><th>股票</th><th>方向</th><th>股数</th><th>成交价 USD</th></tr></thead><tbody>';for(const f of [...a.fills].reverse())html+='<tr><td>'+esc(displayTime(f.executed_at))+'</td><td>'+esc(f.ticker)+'</td><td>'+(f.side==='BUY'?'买入':'卖出')+'</td><td>'+esc(f.quantity)+'</td><td>'+esc(display(f.price))+'</td></tr>';html+='</tbody></table></details>';}
 html+='</section>';

 html+='<details data-account-disclosure="broker-order"><summary>已在券商挂单，记录未成交委托</summary><p>仅记账，不向券商下单。若已部分成交，请先录成交，再记录剩余未成交股数。记录后请更新券商显示的可用现金。</p><form data-form="order"><label>券商订单编号 <input name="order_id" required autocomplete="off"></label><label>股票 <input name="ticker" list="strategy-fill-tickers" value="'+esc(defaultTicker)+'" required autocomplete="off"></label><label>方向 <select name="side"><option value="BUY">买入</option><option value="SELL">卖出</option></select></label><label>当前未成交股数 <input name="quantity" type="number" min="1" step="1" required></label><label>限价 USD <input name="limit_price" inputmode="decimal" required></label><label>每股费用预留 USD <input name="fee_per_share" value="0" inputmode="decimal" required></label><button '+disabled+'>记录已挂委托</button></form></details>';
 if(a.orders.length){html+='<details data-account-disclosure="open-orders"><summary>未结订单</summary>';for(const o of a.orders)html+='<p>'+esc(o.ticker)+' · '+(o.side==='BUY'?'买入':'卖出')+' '+esc(o.remaining_quantity)+' 股 <button type="button" data-action="cancel" data-order="'+esc(o.order_id)+'" '+disabled+'>已在券商撤单，记录撤销</button></p>';html+='</details>';}
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
 let model={loaded:false,account:null,busy:false,message:''},generation=0,retry=null,recommendedTickers=[],reconciliation=pendingFillStore?.read()||null,valuationPromise=null,valuationGeneration=0,valuationPromiseGeneration=-1;
 if(reconciliation)retry={...reconciliation};
 const snapshot=()=>structuredClone({...model,recommendedTickers});
 const emit=()=>onRender(render({...model,recommendedTickers}),snapshot());
 function invalidate(){valuationGeneration++;model.performance=null;model.valuation=null;model.valuationLoading=false;onInvalidate();}
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
  if(data.reconcile_before_retry===true||data.write_may_have_occurred===true)throw issue('RECONCILE_REQUIRED');if(!response.ok||data.status==='BLOCKED'){const error=issue(data.reason||'保存未确认，请刷新核对后再试。');if(body!==undefined&&response.status>=400&&response.status<500)error.definitive_write_rejection=true;throw error;}return data;
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
   const original=saved?JSON.parse(saved.key):null;
   const intent=original?.fields;
   const recorded=reconciliation&&(intent?.kind==='ORDER_OPEN'?account?.orders?.some(o=>o.order_id===intent.order_id&&o.ticker===intent.ticker&&o.side===intent.side&&o.quantity===intent.quantity&&equalAmount(o.limit_price,intent.limit_price)&&equalReserve(o,intent)):!['CANCEL','ORDER_OPEN'].includes(intent?.kind)&&account?.fills?.some(fill=>fill.fill_id===reconciliation.eventId));
   const pendingFill=!!saved&&!recorded&&account?.revision===JSON.parse(saved.key).expected;
   // Original revision may still have a write in flight. Exact recorded order/fill
   // or changed CAS revision resolves it; cancellation is never inferred from absence.
   if(saved&&!pendingFill)pendingFillStore.clear(saved.eventId);
   model={...model,loaded:true,account,busy:false,pendingFill,message:reconciliation?(recorded?(intent?.kind==='ORDER_OPEN'?'已核对：刚才的记录已经保存，请勿重复录入。':'已核对：刚才的成交已经记录，请勿重复录入。'):pendingFill?'上次操作结果仍待确认；请继续核对原记录，勿重新录入。':'账户已刷新，请核对刚才的记录后再操作。'):''};reconciliation=null;
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
  const persistedFill=['DIRECT_FILL','FILL','ORDER_OPEN','CANCEL'].includes(fields.kind)&&pendingFillStore;
  // Persist before sending; retries reuse the original event ID and CAS revision.
  if(persistedFill)pendingFillStore.write({eventId,key});
  const version=++generation;model.busy=true;model.message='';invalidate();emit();
  try{const data=await request(path,body);if(version!==generation)return;let account;try{account=validate(data);if(!account)throw issue('账户保存结果缺失。');if(persistedFill)pendingFillStore.clear(eventId);}catch(_){throw issue('RECONCILE_REQUIRED');}model={loaded:true,account,busy:false,message:fields.kind?.includes('FILL')?'成交已记录。':fields.kind==='ORDER_OPEN'?'委托已记录。请在今日建议更新券商显示的可用现金，无需手动加回挂单占款。':'记录已保存，旧建议已撤下。'};retry=null;emit();await automaticValuation();return data;}
  catch(e){if(version===generation){if(e.definitive_write_rejection&&persistedFill){pendingFillStore.clear(eventId);retry=null;}model.message=errors[e.code]||e.message;if(e.code==='RECONCILE_REQUIRED'){reconciliation={eventId};model.loaded=false;model.account=null;}else if(e.code==='STALE_REVISION'||e.code==='EVENT_ID_CONFLICT'){model.loaded=false;model.account=null;retry=null;}}throw e;}
  finally{if(version===generation){model.busy=false;emit();}}
 }
 const requireAccount=()=>{if(reconciliation||model.pendingFill)throw issue('RECONCILE_REQUIRED');if(!model.loaded||!model.account)throw issue('请先启用并读取新策略账户。');};
 async function automaticValuation(){
  if(!automaticValuationEnabled)return;
  try{await valuation(true);}catch(_){/* Valuation failure must never turn a successful save into a failed save. */}
 }
 function valuation(quiet=false){
  if(valuationPromise&&valuationPromiseGeneration===valuationGeneration)return valuationPromise;
  const pending=performValuation(quiet).finally(()=>{if(valuationPromise===pending)valuationPromise=null;});
  valuationPromise=pending;valuationPromiseGeneration=valuationGeneration;
  return pending;
 }
 async function performValuation(quiet=false){
  requireAccount();if(model.busy||model.valuationLoading)throw issue('BUSY');
  const revision=model.account.revision,version=valuationGeneration;model.valuationLoading=true;if(!quiet)model.message='正在读取持仓估值…';emit();
  try{const data=await request('/valuation');if(version!==valuationGeneration)return;
   if(data.account_revision!==revision||model.account?.revision!==revision||!Array.isArray(data.holdings))throw issue('STALE_REVISION');
   const waiting={EMPTY_HOLDINGS:'当前没有持仓，无需更新市值。',WAIT_SAVED_TARGET:'等待已保存策略目标，暂按成本显示。',WAIT_REGULAR_SESSION:'美股常规交易时段可更新市值，暂按成本显示。'};
   if(Object.hasOwn(waiting,data.status)){model.performance=null;model.valuation=null;model.message=waiting[data.status];return;}
   if(data.status!=='READY')throw issue('估值响应不完整。');
   model.valuation=data;if(!quiet)model.message='估值已更新。';
   model.performance=null;
   try{const performance=await request('/restart-performance');if(version===valuationGeneration&&model.account?.revision===revision&&performance.account_revision===revision){
    const shared=performance.valuation_snapshot;
    if(performance.status==='READY_RECONCILED_NO_EXTERNAL_FLOW'&&shared?.status==='READY'&&shared.account_revision===revision&&Array.isArray(shared.holdings)&&shared.valued_at===performance.as_of&&String(shared.strategy_total)===String(performance.current_equity)){
     model.valuation=shared;model.performance=performance;
    }
   }}catch(_){/* Missing or unverified performance must not invalidate a valid account valuation. */}
  }catch(e){if(version===valuationGeneration){model.performance=null;model.valuation=null;model.message=quiet?'市值暂不可用，当前按成本显示。':errors[e.code]||e.message;}throw e;}
  finally{if(version===valuationGeneration){model.valuationLoading=false;emit();}}
 }
 return {
  load,valuation,refresh:async()=>{if(model.busy)return;const reconciling=Boolean(reconciliation);await load();if(!reconciling&&model.loaded&&model.account)await automaticValuation();},getState:snapshot,
  recoverFill:async()=>{
   if(model.busy)throw issue('BUSY');
   await load();
   if(!model.loaded||!model.account)throw issue('RECONCILE_REQUIRED');
   const saved=pendingFillStore?.read();if(!saved)return;
   const original=JSON.parse(saved.key);
   if(original.path!=='/events'||!['DIRECT_FILL','FILL','ORDER_OPEN','CANCEL'].includes(original.fields?.kind)||original.expected!==model.account.revision)throw issue('RECONCILE_REQUIRED');
   return mutate(original.path,original.fields);
  },
  setRecommendedTickers:tickers=>{const next=[...new Set((Array.isArray(tickers)?tickers:[]).map(t=>String(t).trim().toUpperCase()).filter(t=>/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(t)))];if(JSON.stringify(next)===JSON.stringify(recommendedTickers))return;recommendedTickers=next;emit();},
  initialize:()=>{if(!model.loaded||model.account)throw issue('请先读取账户状态。');return mutate('/initialize',{});},
  confirmCash:({amount:value})=>{requireAccount();return mutate('/events',{kind:'CASH_CONFIRM',amount:amount(value),cash_basis:'AVAILABLE_AFTER_RESERVATIONS'});},
  recordOrder:input=>{
   requireAccount();const ticker=String(input.ticker).trim().toUpperCase(),side=input.side,order_id=String(input.order_id).trim();
   if(!order_id||!/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(ticker)||!['BUY','SELL'].includes(side))throw issue('请检查订单编号、股票和方向。');
   const limit_price=amount(input.limit_price);if(Number(limit_price)<=0)throw issue('限价必须大于零。');
   return mutate('/events',{kind:'ORDER_OPEN',order_id,ticker,side,quantity:shares(input.quantity),limit_price,fee_per_share:amount(input.fee_per_share??'0')});
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
  dispose:()=>{generation++;valuationGeneration++;model.loaded=false;model.account=null;model.valuationLoading=false;model.performance=null;model.valuation=null;}
 };
}
function tradeProfitText(row,valuation){
 const number=v=>{const p=String(v).split('/');return Number(p[0])/(p.length===2?Number(p[1]):1);};
 const signed=v=>(v>0?'+':v<0?'-':'')+'$'+display(Math.abs(v));
 const buy=row.buy_quantity?number(row.buy_amount)/row.buy_quantity:null;
 const sell=row.sell_quantity?number(row.sell_amount)/row.sell_quantity:null;
 const quote=valuation?.holdings?.find(h=>h.security_id===row.security_id);
 const unrealized=row.quantity===0?0:quote?number(quote.price)*row.quantity-number(row.gross_cost):null;
 return '买入均价 '+(buy===null?'—':'$'+display(buy))+' · 卖出均价 '+(sell===null?'—':'$'+display(sell))+
  ' · 已实现 '+signed(number(row.realized_gross))+' · 持仓浮盈亏 '+(unrealized===null?'待更新市值':signed(unrealized));
}
function mountTradeCharts(host,fetchImpl){
 let charts=[],key=null,metrics=[];
 return {update(state){
  const a=state.account;if(!a)return;
  const fresh=state.valuation?.account_revision===a.revision&&Number.isFinite(Date.parse(state.valuation.valued_at))&&Date.now()-Date.parse(state.valuation.valued_at)>=0&&Date.now()-Date.parse(state.valuation.valued_at)<=120000?state.valuation:null;
  const nextKey=JSON.stringify([a.revision,a.fill_correction_revision]);
  if(key!==nextKey){
   charts.forEach(c=>c.destroy());charts=[];metrics=[];host.replaceChildren();key=nextKey;
   const note=document.createElement('p');note.className='muted';note.textContent='按已录成交计算价差盈亏，未扣费用；不等于账户净收益。';host.append(note);
   const rows=[...(a.trade_results||[])].reverse();
   for(const row of rows){
    const section=document.createElement('section');section.style.cssText='margin:20px 0';
    const metric=document.createElement('p');metric.style.cssText='font-size:15px;line-height:1.8;font-weight:600';section.append(metric);metrics.push({metric,row});
    const card=document.createElement('div');section.append(card);host.append(section);
    const revision=a.revision,renderKey=nextKey;
    const chart=root.SelectedStockCharts.createSelectedStockCharts(card,async(ticker,interval,signal)=>{
     const query=new URLSearchParams({security_id:row.security_id,interval,bars:'260'});
     const response=await fetchImpl('/api/strategy-display/latest-bars?'+query,{signal,cache:'no-store'});
     if(!response.ok)throw Error('成交历史行情暂不可用');const data=await response.json();
     if(key!==renderKey||data.account_revision!==revision||data.security_id!==row.security_id||data.ticker!==ticker)throw Error('账户已变化，请刷新成交图表');
     if(data.status!=='DISPLAY_ONLY'||data.executable!==false||!Array.isArray(data.bars)||!data.bars.length||data.bars.length>260)throw Error('成交历史行情校验失败');
     return {...data,status:'AVAILABLE',display_only:true,daily_as_of:data.as_of,latest_quote:{price:Number(data.price),as_of:Number.isFinite(data.price_time)?new Date(data.price_time*1000).toISOString():null,session:data.price_session==='REGULAR'?'REGULAR_LAST':'DAILY_BAR'}};
    });
    chart.setFills(a.fills||[]);chart.setSelection({trade_history:true,label:'真实成交 · 展示行情',stocks:[{security_id:row.security_id,ticker:row.ticker,quantity:row.quantity}]});charts.push(chart);
   }
  }
  metrics.forEach(({metric,row})=>{metric.textContent=row.ticker+' · '+tradeProfitText(row,fresh);});
 }};
}
function mount({container,initialValuation=true,...options}){
 const tradeHost=document.createElement('div');const tradeCharts=root.SelectedStockCharts?mountTradeCharts(tradeHost,options.fetchImpl||root.fetch.bind(root)):null;
 let lastClearedSuccess=null;const retainedDrafts=new Map(),retainedDisclosures=new Map();
 const controller=createController({...options,onRender:(html,state)=>{
  for(const form of container.querySelectorAll('form[data-form]'))retainedDrafts.set(form.dataset.form,Object.fromEntries(new FormData(form)));
  const drafts=[...retainedDrafts].map(([kind,fields])=>({kind,fields}));
  for(const n of container.querySelectorAll('details[data-account-disclosure]'))if(n.dataset.accountDisclosure)retainedDisclosures.set(n.dataset.accountDisclosure,n.open);
  const disclosureStates=[...retainedDisclosures];
  container.innerHTML=html;
  for(const [key,open] of disclosureStates){const n=container.querySelector('details[data-account-disclosure="'+key+'"]');if(n)n.open=open;}
  const success=!state.busy&&['成交已记录。','记录已保存，','委托已记录。'].some(prefix=>state.message.startsWith(prefix));
  const successKey=success?JSON.stringify([state.account?.revision,state.message]):null;
  const clearOnce=success&&successKey!==lastClearedSuccess;if(clearOnce)lastClearedSuccess=successKey;
  const clearedForm=clearOnce?(state.message.startsWith('成交已记录。')?'fill':state.message.startsWith('委托已记录。')?'order':null):null;
  if(clearedForm)retainedDrafts.delete(clearedForm);
  {
   for(const draft of drafts){if(draft.kind===clearedForm)continue;const form=container.querySelector(`form[data-form="${draft.kind}"]`);if(form)for(const [name,value] of Object.entries(draft.fields)){const input=form.elements.namedItem(name);if(input&&!(draft.kind==='fill'&&name==='ticker'&&!value))input.value=value;}}
  }
  if(tradeCharts){const slot=container.querySelector('[data-trade-charts]');if(slot){slot.append(tradeHost);tradeCharts.update(state);}}
  options.onRender?.(html,state);
 }});
 const show=e=>{const status=container.querySelector('[role="status"]');if(status)status.textContent=errors[e.code]||e.message;else{const p=document.createElement('p');p.setAttribute('role','status');p.textContent=errors[e.code]||e.message;container.prepend(p);}};
 container.addEventListener('submit',async e=>{const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();const data=Object.fromEntries(new FormData(form));try{await(form.dataset.form==='cash'?controller.confirmCash(data):form.dataset.form==='order'?controller.recordOrder(data):controller.recordFill(data));}catch(error){show(error);}});
 container.addEventListener('click',async e=>{const button=e.target.closest('button[data-action]');if(!button)return;try{if(button.dataset.action==='refresh')await controller.load();else if(button.dataset.action==='recover-fill')await controller.recoverFill();else if(button.dataset.action==='valuation')await controller.valuation();else if(button.dataset.action==='enable')await controller.initialize();else if(button.dataset.action==='cancel')await controller.cancel(button.dataset.order);}catch(error){show(error);}});
 controller.ready=initialValuation?controller.refresh():controller.load();return controller;
}
root.StrategyAccountUI={createController,browserPendingFillStore,render,beijingTime,displayTime,tradeProfitText,mountTradeCharts,mount};
if(typeof module!=='undefined')module.exports=root.StrategyAccountUI;
})(typeof window!=='undefined'?window:globalThis);
