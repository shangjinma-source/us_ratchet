(function(root){
'use strict';
const API='/api/strategy-account/target';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const messages={INCOMPLETE_MARK_DOMAIN:'部分候选股票的当日报价未通过核验，暂未生成目标。请检查网络及电脑时间同步后重试；已保存现金仍保留。',CURRENT_MONTH_TRAINING_DEPLOYMENT_REQUIRED:'本月训练数据未就绪，请等待数据准备完成。',TARGET_REASON_MONTH_MISMATCH:'目标月份与操作不匹配，请重新读取目标后配置。',REQUOTE_REQUIRED:'报价已过期，请刷新建议。',CASH_RECONFIRMATION_REQUIRED:'请先确认最新现金。',STALE_REVISION:'账户已变化，请读取最新账户后刷新。',STALE_TARGET:'目标已变化，请重新读取目标。',MONTHLY_TARGET_REQUIRED:'需要本月目标，请明确选择跨月配置。',NO_MONTHLY_TARGET:'尚未生成账户目标。'};
function money(value){const parts=String(value??'').split('/');const n=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return Number.isFinite(n)?n.toLocaleString('en-US',{maximumFractionDigits:2}):'待核验';}
function persistentRows(m){
 const rows=new Map(),add=x=>{if(!x?.security_id)return;const row=rows.get(x.security_id)||{security_id:x.security_id,ticker:x.ticker||x.security_id,held:0,target:m.target?0:null,buy:0,sell:0};if(x.ticker)row.ticker=x.ticker;rows.set(x.security_id,row);return row;};
 for(const x of m.target?.targets||[])add(x).target=x.quantity;
 for(const x of m.account?.holdings||[])add(x).held=x.quantity;
 for(const x of m.account?.orders||[]){const r=add(x);if(r&&(!x.status||x.status==='OPEN')&&Number.isSafeInteger(x.remaining_quantity)&&x.remaining_quantity>0){if(x.side==='BUY')r.buy+=x.remaining_quantity;else if(x.side==='SELL')r.sell+=x.remaining_quantity;}}
 if(!rows.size)return '';
 const bound=m.preview?.target_id===m.target?.target_id&&m.preview?.account_revision===m.account?.revision;
 const orders=bound?(m.preview.difference?.new_orders||[]):[],refs=bound?(m.preview.reference_quotes||{}):{};
 const fresh=bound&&m.fresh&&m.account?.cash_confirmation_valid&&!m.busy&&!m.cashBusy;
 const price=value=>{const parts=String(value??'').split('/');const n=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return value!==null&&value!==undefined&&parts.length<=2&&Number.isFinite(n)&&n>0?'$'+esc(money(value)):'待刷新';};
 let html='<div class="monthly-table-scroll"><table><thead><tr><th>股票</th><th>实际持有</th><th>目标股数</th><th>待买 / 待卖</th><th>买入参考 USD</th><th>卖出参考 USD</th><th>今日动作</th><th>报价状态</th></tr></thead><tbody>';
 for(const r of rows.values()){
  const active=orders.filter(o=>o.security_id===r.security_id),ref=refs[r.security_id]||{};
  const buy=active.find(o=>o.side==='BUY'),sell=active.find(o=>o.side==='SELL');
  const buyPrice=Object.hasOwn(ref,'buy_limit')?ref.buy_limit:buy?.limit_price,sellPrice=Object.hasOwn(ref,'sell_limit')?ref.sell_limit:sell?.limit_price;
  let action='待刷新后判断';
  if(!m.account?.cash_confirmation_valid)action='确认最新余额后计算差额';
  else if(!m.target)action='先生成本月目标';
  else if(m.target.server_month&&m.target.server_month!==m.target.target_month)action='需要本月目标';
  else if(fresh){
   if(m.preview.difference?.cancel_before_recalculate?.length)action='先核实冲突挂单，撤单后重算';
   else if(active.length)action=active.map(o=>(o.side==='BUY'?'等回落，限价买入最多 ':'按减仓目标，限价卖出 ')+o.quantity+' 股').join('；');
   else if(r.buy||r.sell)action='等待已记录挂单；不重复下单';
   else if(r.held===r.target)action='持有；本次无需新增订单';
   else action='本次未生成订单；检查现金或差额状态';
  }
  const time=ref.observed_at||buy?.observed_at||sell?.observed_at;
  const deadline=ref.reference_valid_until||buy?.reference_valid_until||sell?.reference_valid_until||m.preview?.reference_valid_until;
  const hasPrice=price(buyPrice)!=='待刷新'||price(sellPrice)!=='待刷新';
  const rowFresh=fresh&&Number.isFinite(Date.parse(deadline))&&Date.parse(deadline)>(m.renderedAt??Date.now());
  const state=hasPrice?(rowFresh?'本次参考；操作前核对':'旧参考，待刷新；不可作为有效单'):'待刷新报价';
  html+='<tr><td>'+esc(r.ticker)+'</td><td>'+esc(r.held)+'</td><td>'+esc(r.target??'待配置')+'</td><td>'+esc(r.buy)+' / '+esc(r.sell)+'</td><td>'+price(buyPrice)+'</td><td>'+price(sellPrice)+'</td><td>'+esc(action)+'</td><td>'+esc(state)+(time?'<br>报价 '+esc(time):'')+(deadline?'<br>有效至 '+esc(deadline):'')+'</td></tr>';
 }
 return html+'</tbody></table></div>';
}
function render(m){
 let html='<section class="strategy-monthly-target"><h3>今日买卖建议</h3>';
 const disabled=(m.busy||m.cashBusy)?'disabled':'';
 const eligible=m.account?.cash_confirmation_valid===true&&!m.busy&&!m.cashBusy;
 if(m.account)html+='<form data-form="configure-cash"><label>本次可用现金 USD <input name="amount" inputmode="decimal" required autocomplete="off"></label> <input type="hidden" name="cash_basis" value="AVAILABLE_AFTER_RESERVATIONS"> <button '+disabled+'>更新现金并查看建议</button></form>';
 html+='<div class="monthly-action-header"><h4>本月股票与今日动作</h4><div><button data-action="load" type="button" '+disabled+'>刷新状态</button>';
 if(m.target)html+='<button data-action="preview" type="button" '+(eligible?'':'disabled')+'>刷新买卖建议</button>';
 else if(eligible)html+='<button data-action="INITIAL" type="button">生成初始目标</button>';
 html+='</div></div><div class="monthly-action-status" aria-live="polite">';
 if(!m.loaded)html+='正在读取账户与目标…';
 else if(!m.account)html+='请先在操作与持仓页启用新策略账户。';
 else if(!m.account.cash_confirmation_valid){
  const estimate=m.account.cash_summary?.derived_total_uninvested_cash_estimate;
  html+='现金待确认';
  if(estimate!==null&&estimate!==undefined)html+=' · 成交后估算 <strong>$'+esc(money(estimate))+'</strong>（待券商核对）';
  html+=' · 填写上方余额后配置';
 }else if(!m.target)html+='现金已确认 · 待生成本月目标';
 else html+='目标月份 '+esc(m.target.target_month)+' · 配置时净值 $'+esc(money(m.target.strategy_equity));
 html+='</div>';
 const routine=['尚无已保存目标。','账户已更新，请刷新建议。','已读取保存的目标，尚未刷新买卖建议。','已扣除新策略持仓及剩余挂单；请核对后自行操作。'];
 if(m.message&&!routine.includes(m.message))html+='<p role="status">'+esc(m.message)+'</p>';
 html+=persistentRows(m);

 if(m.preview&&m.preview.target_id===m.target?.target_id&&m.preview.account_revision===m.account?.revision){
  html+='<section class="monthly-options"><h4>买卖明细 · '+(m.fresh?'本次查询结果，操作前请刷新':'待刷新（保留旧显示）')+'</h4>'; 
  const d=m.preview.difference,names=Object.fromEntries([...(m.target?.targets||[]),...(m.account?.holdings||[]),...(m.account?.orders||[])].map(x=>[x.security_id,x.ticker]));
  if(d.cancel_before_recalculate?.length)html+='<p>已有挂单与目标冲突，请先在券商核实撤单并更新账户，再重新计算。</p>';
  html+='<div class="monthly-table-scroll"><table><thead><tr><th>股票</th><th>方向</th><th>股数</th><th>建议限价 USD</th><th>报价时间</th><th>有效至</th><th>说明</th></tr></thead><tbody>';
  for(const order of d.new_orders||[])html+='<tr><td>'+esc(order.ticker||names[order.security_id]||order.security_id)+'</td><td><span class="trade-side '+(order.side==='BUY'?'buy':'sell')+'">'+(order.side==='BUY'?'买入':'卖出')+'</span></td><td>'+esc(order.quantity)+'</td><td>'+esc(money(order.limit_price))+'</td><td>'+esc(order.observed_at||'未提供')+'</td><td>'+esc(order.reference_valid_until||'未提供')+'</td><td>'+esc([order.execution_reason,order.strategy_reason].filter(Boolean).join('；'))+'</td></tr>';
  html+='</tbody></table></div>';
  if(!(d.new_orders||[]).length)html+='<p>本次结果没有新增订单；这不表示已有挂单成交。</p>';
  if(d.waiting_cash?.length)html+='<p>部分买入等待可用现金；未成交卖款不会提前用于买入。</p>';
  html+='</section>'; 
 }
 return html+'</section>';
}
// Browser persistence contains display fields only, never evidence paths or executable orders.
const REFERENCE_CACHE_KEY='ratchet.monthly-reference.v1',REFERENCE_CACHE_LIMIT=100000;
function referenceSnapshot(value){
 if(!value||typeof value.target_id!=='string'||typeof value.account_revision!=='string'||value.target_id.length>256||value.account_revision.length>256)return null;
 const text=v=>typeof v==='string'&&v.length<=256?v:null;
 const price=v=>{const parts=String(v??'').split('/'),n=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return v!==null&&v!==undefined&&parts.length<=2&&Number.isFinite(n)&&n>0&&String(v).length<=80?String(v):null;};
 const date=v=>typeof v==='string'&&v.length<=40&&Number.isFinite(Date.parse(v))?v:null;
 const refs=value.reference_quotes||{},orders=value.difference?.new_orders||[];
 if(typeof refs!=='object'||Array.isArray(refs)||!Array.isArray(orders)||Object.keys(refs).length>512||orders.length>512)return null;
 const quotes=Object.create(null),newOrders=[];
 for(const [id,q] of Object.entries(refs)){if(!text(id)||!q||typeof q!=='object')return null;quotes[id]={buy_limit:price(q.buy_limit),sell_limit:price(q.sell_limit),observed_at:date(q.observed_at),reference_valid_until:date(q.reference_valid_until)};}
 for(const o of orders){if(!o||!text(o.security_id)||!['BUY','SELL'].includes(o.side)||!Number.isSafeInteger(o.quantity)||o.quantity<=0)return null;newOrders.push({security_id:o.security_id,ticker:text(o.ticker),side:o.side,quantity:o.quantity,limit_price:price(o.limit_price),observed_at:date(o.observed_at),reference_valid_until:date(o.reference_valid_until)});}
 return {target_id:value.target_id,account_revision:value.account_revision,reference_valid_until:date(value.reference_valid_until),reference_quotes:quotes,difference:{new_orders:newOrders}};
}
function browserStorage(){try{return root.localStorage;}catch{return null;}}
function createController({fetchImpl=root.fetch?.bind(root),onRender=()=>{},onTargetChanged=()=>{},onAccountChanged=()=>{},saveCash=null,storage=browserStorage(),now=()=>Date.now(),makeId=()=>root.crypto.randomUUID()}={}){
 const model={loaded:false,target:null,configurationReason:null,account:null,preview:null,fresh:false,busy:false,cashBusy:false,reconciliationRequired:false,message:''};let generation=0,retry=null,expiryTimer=null;
 const restoreReference=()=>{
  if(model.preview||!model.account?.revision||!model.target?.target_id)return;
  try{const raw=storage?.getItem(REFERENCE_CACHE_KEY);if(!raw||raw.length>REFERENCE_CACHE_LIMIT)return;const saved=JSON.parse(raw);if(saved.version!==1||saved.account_id!==(model.account.account_id??null))return;const cached=referenceSnapshot(saved.preview);if(cached?.account_revision!==model.account.revision||cached?.target_id!==model.target.target_id)return;model.preview=cached;model.fresh=false;}catch{/* Storage is optional and untrusted. */}
 };
 const saveReference=()=>{try{const preview=referenceSnapshot(model.preview);if(!preview)return;const raw=JSON.stringify({version:1,account_id:model.account?.account_id??null,preview});if(raw.length<=REFERENCE_CACHE_LIMIT)storage?.setItem(REFERENCE_CACHE_KEY,raw);}catch{/* Quota/private browsing must not prevent quoting. */}};
 const draw=()=>{model.renderedAt=now();onRender(render(model),structuredClone(model));};
 const cancelExpiry=()=>{if(expiryTimer!==null)clearTimeout(expiryTimer);expiryTimer=null;};
 const fail=code=>{throw Error(code);};
 const uncertain=error=>error?.write_may_have_occurred===true||error?.reconcile_before_retry===true;
 async function request(path,body){const response=await fetchImpl(path.startsWith('/api/')?path:API+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});const data=await response.json();if(!response.ok||data.status==='BLOCKED'){const error=Error(data.reason||'请求失败，请重试。');error.write_may_have_occurred=data.write_may_have_occurred===true;error.reconcile_before_retry=data.reconcile_before_retry===true;throw error;}return data;}
 async function reconcile(token){
  const envelope=await request('/api/strategy-account'),response=await request(''),saved=target(response),updated=envelope.account;
  if(token!==generation)return false;
  if(envelope.status!=='READY'||typeof updated?.revision!=='string'||!Array.isArray(updated.holdings)||!Array.isArray(updated.orders))fail('INVALID_ACCOUNT_RESPONSE');
  model.account=structuredClone(updated);model.configurationReason=response.configuration_reason||(saved?null:'INITIAL');
  if(model.target?.target_id!==saved?.target_id)model.preview=null;
  model.target=saved;model.loaded=true;model.fresh=false;restoreReference();onAccountChanged(updated);onTargetChanged(saved);return true;
 }
 async function uncertainFailure(error,token){
  model.reconciliationRequired=true;model.fresh=false;cancelExpiry();
  try{await reconcile(token);model.message='操作可能已保存，已读取账户和目标供核对；请点击刷新状态完成确认，暂不重复提交。';}
  catch{model.message='操作可能已保存，但账户或目标核对未成功；请先刷新状态核对，暂不重复提交。';}
 }
 async function action(fn){if(model.busy)fail('正在处理，请勿重复提交。');const token=++generation;model.busy=true;model.fresh=false;cancelExpiry();draw();try{await fn(token);}catch(error){if(token===generation){if(uncertain(error))await uncertainFailure(error,token);else model.message=model.reconciliationRequired?'操作可能已保存，核对尚未成功；请先刷新目标核对，暂不重复提交。':messages[error.message]||'读取或生成失败，请核对后重试。';draw();}throw error;}finally{if(token===generation){model.busy=false;draw();}}}
 function requireReconciled(){if(model.reconciliationRequired)fail('RECONCILIATION_REQUIRED');}
 function target(data){if(data.status==='NOT_INITIALIZED')return null;if(data.status!=='SAVED_TARGET'||typeof data.target_id!=='string'||!Array.isArray(data.targets))fail('INVALID_TARGET_RESPONSE');return data;}
 function account(){if(!model.account?.revision||!model.account.cash_confirmation_valid)fail('CASH_RECONFIRMATION_REQUIRED');return model.account;}
 const controller={
  getState:()=>structuredClone(model),
  async configureCash(input){
   requireReconciled();if(model.busy||model.cashBusy)fail('正在处理，请勿重复提交。');
   if(typeof saveCash!=='function')fail('现金配置入口尚未接通。');
   const startingRevision=model.account?.revision;let cashSaved=false;model.cashBusy=true;model.fresh=false;cancelExpiry();draw();
   try{
    const updated=await saveCash({...input,cash_basis:'AVAILABLE_AFTER_RESERVATIONS'});cashSaved=true;
    if(model.account?.revision!==startingRevision&&model.account?.revision!==updated.revision)fail('STALE_REVISION');
    controller.setAccount(updated);const loadGeneration=generation+1;await controller.load();
    if(generation!==loadGeneration||model.account?.revision!==updated.revision)fail('STALE_REVISION');
    if(!['INITIAL','EXPLICIT_RECONFIGURE','MONTHLY_SELECTION'].includes(model.configurationReason))fail('CURRENT_MONTH_TRAINING_DEPLOYMENT_REQUIRED');
    await controller.configure(model.configurationReason);
   }catch(error){model.fresh=false;if(uncertain(error)){if(!model.reconciliationRequired)await uncertainFailure(error,generation);throw error;}const detail=messages[error.message]||'配置或报价未完成，请重试。';model.message=cashSaved?'现金已保存；'+detail+' 无需重复确认现金，可使用下方目标或建议按钮重试。':messages[error.message]||'现金保存未确认，请读取账户核对后重试。';throw error;}
   finally{model.cashBusy=false;draw();}
  },
  setAccount(value){cancelExpiry();generation++;model.busy=false;model.fresh=false;model.preview=null;model.account=value?structuredClone(value):null;restoreReference();model.message='账户已更新，请刷新建议。';draw();},
  load:()=>action(async token=>{if(model.reconciliationRequired){if(await reconcile(token)){model.reconciliationRequired=false;retry=null;model.message='已重新读取账户和目标，请核对已保存结果后再选择操作。';}return;}const response=await request(''),data=target(response);if(token!==generation)return;model.configurationReason=response.configuration_reason||(data?null:'INITIAL');if(model.target?.target_id!==data?.target_id)model.preview=null;model.target=data;model.loaded=true;restoreReference();model.message=data?'已读取保存的目标，尚未刷新买卖建议。':'尚无已保存目标。';onTargetChanged(data);}),
  generate(reason){requireReconciled();const a=account();if(!['INITIAL','MONTHLY_SELECTION','EXPLICIT_RECONFIGURE'].includes(reason))fail('INVALID_REASON');
   const fields={reason,expected_revision:a.revision,previous_target_id:model.target?.target_id??null};const key=JSON.stringify(fields);if(!retry||retry.key!==key)retry={key,body:{event_id:makeId(),...fields}};
   return action(async token=>{const data=target(await request('/generate',retry.body));if(token!==generation)return;if(model.target?.target_id!==data?.target_id)model.preview=null;model.target=data;model.loaded=true;restoreReference();retry=null;model.message='目标已保存，请刷新买卖建议。';onTargetChanged(data);});},
  async configure(reason){const revision=model.account?.revision,expectedGeneration=generation+1;await controller.generate(reason);if(generation!==expectedGeneration||model.account?.revision!==revision)fail('STALE_REVISION');await controller.refresh();},
  refresh(){requireReconciled();const a=account(),id=model.target?.target_id;if(!id)fail('NO_MONTHLY_TARGET');const revision=a.revision;
   return action(async token=>{const data=await request('/preview',{expected_revision:revision,target_id:id});if(token!==generation)return;if(data.status!=='READY'||data.target_id!==id||data.account_revision!==revision||!data.difference)fail('RESPONSE_BINDING_MISMATCH');
    if(model.account?.revision!==revision||model.target?.target_id!==id)return;const deadlines=[data.reference_valid_until,...Object.values(data.reference_quotes||{}).map(q=>q.reference_valid_until)].map(Date.parse).filter(Number.isFinite);const deadline=deadlines.length?Math.min(...deadlines):NaN;if((data.difference.new_orders||[]).length&&(!Number.isFinite(deadline)||deadline<=now()))fail('REQUOTE_REQUIRED');model.preview=data;model.fresh=true;saveReference();if(Number.isFinite(deadline))expiryTimer=setTimeout(()=>{model.fresh=false;model.message='报价校验已过期，请刷新建议。';draw();},Math.min(deadline-now(),2147483647));expiryTimer?.unref?.();model.message='已扣除新策略持仓及剩余挂单；请核对后自行操作。';});},
  invalidate(){cancelExpiry();generation++;model.busy=false;model.fresh=false;model.preview=null;model.message='账户或目标已变化，请重新读取并刷新。';draw();},
  dispose(){cancelExpiry();generation++;model.busy=false;model.fresh=false;}
 };draw();return controller;
}
function mount({container,...options}){
 const controller=createController({...options,onRender:(html,state)=>{const form=container.querySelector?.('form[data-form="configure-cash"]');const draft=form?Object.fromEntries(new FormData(form)):null;container.innerHTML=html;if(draft){const next=container.querySelector('form[data-form="configure-cash"]');if(next)for(const [name,value] of Object.entries(draft))next.elements.namedItem(name).value=value;}options.onRender?.(html,state);}});
 const click=event=>{const button=event.target.closest?.('[data-action]');if(!button||!container.contains(button))return;const kind=button.dataset.action;try{const work=kind==='load'?controller.load():kind==='preview'?controller.refresh():controller.configure(kind);Promise.resolve(work).catch(()=>{});}catch(error){options.onError?.(error);}};
 const submit=event=>{const form=event.target.closest?.('form[data-form="configure-cash"]');if(!form||!container.contains(form))return;event.preventDefault();controller.configureCash(Object.fromEntries(new FormData(form))).catch(()=>{});};
 container.addEventListener('submit',submit);
 container.addEventListener('click',click);return {...controller,dispose(){container.removeEventListener('submit',submit);container.removeEventListener('click',click);controller.dispose();}};
}
const api={createController,render,mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StrategyMonthlyTargetUI=api;
})(typeof globalThis!=='undefined'?globalThis:this);
