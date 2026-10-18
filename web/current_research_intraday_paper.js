(function(root){
'use strict';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function money(v){const t=String(v);if(!/^\d+(?:\.\d+)?(?:\/\d+)?$/.test(t))throw Error('金额格式无效');const p=t.split('/'),n=Number(p[0])/(p[1]===undefined?1:Number(p[1]));if(!Number.isFinite(n)||n<0)throw Error('金额无效');return n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function instant(v){if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v)||!Number.isFinite(Date.parse(v)))throw Error('时间须含明确时区偏移，例如 2026-10-15T10:30:00-04:00');return v;}
function fraction(v){const t=String(v);if(!/^\d+(?:\.\d+)?(?:\/\d+)?$/.test(t))throw Error('金额格式无效');let [a,b='1']=t.split('/');const digits=(a.split('.')[1]||'').length;const n=BigInt(a.replace('.','')),d=BigInt(b)*10n**BigInt(digits);if(d<=0n)throw Error('金额分母无效');return [n,d];}
const equal=(a,b)=>a[0]*b[1]===b[0]*a[1];
const add=(a,b)=>[a[0]*b[1]+b[0]*a[1],a[1]*b[1]];
const multiply=(a,n)=>[a[0]*BigInt(n),a[1]];
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const bj=v=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 北京时间';
function beijingInput(v){if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(v))throw Error('请填写北京时间，精确到秒');const iso=v.length===16?v+':00+08:00':v+'+08:00';instant(iso);if(new Date(Date.parse(iso)+8*3600000).toISOString().slice(0,19)!==iso.slice(0,19))throw Error('发生时间无效');return iso;}
function serverMessage(value){
 const text=String(value||'');
 if(/RESELECT_REQUIRED/.test(text))return '已跨月，需先确认新月目标，不能沿用旧目标续单。';
 if(/PRIOR_ORDER_NOT_SETTLED/.test(text))return '旧模拟单尚未完成，请先明确处理旧单。';
 if(/CONTINUITY|ACTION_REVIEW|SOURCE|CAPTURE/.test(text))return '缺少可核对的行情或份额连续性证据，暂不能续单。';
 if(/OUTSIDE_(?:SCHEDULED_|DECLARED_)?REGULAR_SESSION/.test(text))return '当前不在已确认的常规交易时段，暂不能生成模拟挂单。';
 if(/REFERENCE_REFRESHED|REFERENCE_SUPERSEDED|REFERENCE_PROCESS_CHANGED/.test(text))return '行情版本已更新，请手动刷新草案后再操作。';
 if(/NO_AVAILABLE_REPLAYED_REFERENCE|CURRENT_REFERENCE_NOT_READY|LAST_QUOTE_FUTURE/.test(text))return '尚无通过时效核验的盘中行情，请稍后手动刷新；未生成模拟挂单。';
 if(/REFERENCE_NOT_CURRENTLY_ACCEPTABLE|LAST_QUOTE_STALE|EXPIRED/.test(text))return '报价或草案已过期，请刷新后再操作。';
 return '本次模拟操作暂未完成。可恢复账户核对；若结果不明，请重试同一操作。';
}
function create(details,body,fetcher,uuid,onOpen=()=>{},clock={now:()=>Date.now(),set:(f,n)=>setTimeout(f,n),clear:id=>clearTimeout(id)}){
 let research=null,payload=null,generation=0,busy=false,controller=null,expiry=null,retry=null,error='',draft={},parentOpen=true;
 function stop(){generation++;if(controller)controller.abort();controller=null;if(expiry)clock.clear(expiry);expiry=null;busy=false;payload=null;retry=null;error='';}
 function selected(security){const candidates=research.selected_security?[research.selected_security]:(research.stocks||[]);return security&&candidates.some(s=>s.ticker===security.ticker&&s.security_id===security.security_id);}
 function budget(){return fraction(research.budget_identity_exact ? research.budget_identity_exact.entered_cash : research.budget);}
 function validate(d){
  if(!d||d.research_id!==research.research_id||d.research_only!==true||d.execution_blocked!==true||d.real_account!==false||d.account_id!=='intraday-'+research.research_id||!['PROPOSAL','EXISTING_ACCOUNT','ACCOUNT','CONTINUATION_PROPOSAL','PENDING_UNIT_REVIEW'].includes(d.status))throw Error('盘中模拟账户版本不一致');
  if(d.status==='PENDING_UNIT_REVIEW'){validate({...d,status:'ACCOUNT',proposal:null});if(d.proposal!==null||!d.review_reference||!hash(d.review_reference.event_sha256))throw Error('待核验版本无效');instant(d.review_reference.checked_at);instant(d.review_reference.accept_before);if(Date.parse(d.review_reference.checked_at)>Date.parse(d.review_reference.accept_before))throw Error('待核验时点无效');return d;}
  const continuation=d.status==='CONTINUATION_PROPOSAL';
  if(continuation)validate({...d,status:'ACCOUNT',proposal:null});
  if(d.status==='PROPOSAL'||continuation){
   const p=d.proposal;if(!p||p.research_id!==research.research_id||!hash(p.proposal_id)||(continuation?p.account_revision!==d.account.revision:p.account_revision!=='INTRADAY_INITIAL_CASH_V1')||!p.security||!selected(p.security)||!Number.isSafeInteger(p.quantity)||p.quantity<0)throw Error('模拟草案目标无效');
   if(continuation&&(p.proposal_kind!=='CONTINUATION'||!Number.isSafeInteger(p.target_quantity)||p.target_quantity<0||p.target_quantity!==d.account.target_quantity||!Number.isSafeInteger(p.held_quantity)||p.held_quantity!==Number(d.account.shares[p.security.security_id]||0)||(!d.account.closed&&d.account.filled_quantity<d.account.order.quantity)))throw Error('续单目标或旧单状态不一致');
   if(continuation&&p.action!==(p.target_quantity<=p.held_quantity?'NO_ACTION':p.quantity===0?'WAIT_CASH':'PROPOSE_BUY'))throw Error('续单状态不一致');
   const cap=fraction(p.limit_price),cash=fraction(p.available_cash);const affordable=cap[0]>0n?(cash[0]*cap[1])/(cash[1]*cap[0]):0n;const deficit=continuation?BigInt(Math.max(0,p.target_quantity-p.held_quantity)):affordable;const expected=affordable<deficit?affordable:deficit;if(cap[0]<=0n||BigInt(p.quantity)!==expected)throw Error('草案整股数量不符全额现金');
   ['limit_price','notional','residual_cash','available_cash'].forEach(k=>money(p[k]));instant(p.accept_before);instant(p.reference_valid_until);instant(p.proposal_created_at);
   if(!p.market_session||p.time_in_force!==null)throw Error('草案时段无效');instant(p.market_session.close_at);
   if(Date.parse(p.proposal_created_at)>Date.parse(p.accept_before)||Date.parse(p.accept_before)>Date.parse(p.reference_valid_until)||Date.parse(p.reference_valid_until)>Date.parse(p.market_session.close_at))throw Error('草案采纳时序无效');
   if(!equal(fraction(p.available_cash),continuation?fraction(d.account.cash):budget())||!equal(fraction(p.notional),multiply(fraction(p.limit_price),p.quantity))||!equal(add(fraction(p.notional),fraction(p.residual_cash)),fraction(p.available_cash)))throw Error('草案现金预算不一致');
  }else{
   const a=d.account;if(!a||a.research_id!==research.research_id||!hash(a.revision)||!hash(a.acceptance_id)||!hash(a.proposal_id)||a.account_id!==d.account_id||!a.order||typeof a.order.order_id!=='string'||!a.security||!selected(a.security)||a.order.side!=='BUY'||a.order.order_id!==(a.current_order_acceptance_id||a.acceptance_id)+':BUY'||(a.current_order_acceptance_id&&!hash(a.current_order_acceptance_id))||(a.original_acceptance_id&&a.original_acceptance_id!==a.acceptance_id)||a.order.security_id!==a.security.security_id||!Number.isSafeInteger(a.order.quantity)||a.order.quantity<=0||!Number.isSafeInteger(a.filled_quantity)||a.filled_quantity<0||a.filled_quantity>a.order.quantity)throw Error('模拟订单版本无效');
   ['cash','reserved_cash','fees'].forEach(k=>money(a[k]));money(a.order.limit);instant(a.order.session_close);instant(a.order.accepted_at);if(a.order.time_in_force!=='DAY'||Date.parse(a.order.accepted_at)>=Date.parse(a.order.session_close))throw Error('模拟单有效时段无效');
   if(![null,'CANCEL','EXPIRE'].includes(a.closed)||!a.shares||Object.entries(a.shares).some(([sid,q])=>sid!==a.security.security_id||!Number.isSafeInteger(q)||q<0)||Number(a.shares[a.security.security_id]||0)<a.filled_quantity)throw Error('模拟份额不一致');
   if(!equal(fraction(a.reserved_cash),multiply(fraction(a.order.limit),a.closed?0:a.order.quantity-a.filled_quantity)))throw Error('模拟预留不一致');
   if(fraction(a.reserved_cash)[0]*fraction(a.cash)[1]>fraction(a.cash)[0]*fraction(a.reserved_cash)[1])throw Error('模拟现金不足');
   if(!Array.isArray(a.events))throw Error('模拟事件缺失');
   if(!equal(fraction(a.initial_cash),budget())||!equal(add(add(fraction(a.cash),fraction(a.recorded_buy_notional)),fraction(a.fees)),fraction(a.initial_cash)))throw Error('模拟现金恒等式不一致');
   let recentFilled=0,recentFees=[0n,1n],recentCost=[0n,1n];
   for(const e of a.events){if(e.kind==='FILL'){if(!Number.isSafeInteger(e.quantity)||e.quantity<=0)throw Error('模拟成交数量无效');recentFilled+=e.quantity;recentFees=add(recentFees,fraction(e.fees));recentCost=add(recentCost,multiply(fraction(e.price),e.quantity));}}
   const le=(x,y)=>x[0]*y[1]<=y[0]*x[1];
   if(recentFilled>Number(a.shares[a.security.security_id]||0)||!le(recentFees,fraction(a.fees))||!le(recentCost,fraction(a.recorded_buy_notional)))throw Error('近期模拟事件超过累计');
   if(payload&&payload.account&&payload.account_id!==d.account_id)throw Error('模拟账户发生变化');
  }
  return d;
 }
 function deadline(){return payload&&payload.proposal?Math.min(Date.parse(payload.proposal.accept_before),Date.parse(payload.proposal.reference_valid_until)):0;}
 function render(){
  for(const k of ['quantity','price','fees','eventTime']){const el=body.querySelector('[name="'+k+'"]');if(el)draft[k]=el.value;}
  const expired=!!(payload&&payload.proposal&&clock.now()>=deadline());
  const p=payload&&!expired&&payload.proposal,a=payload&&payload.account;
  body.innerHTML='<p class="preview-caption">独立纸面模拟，不是券商真实挂单；不写实盘。发生时间统一填写北京时间（+08:00，精确到秒）；不使用设备本地时区。</p>'+(error?'<p class="info-strip">'+esc(error)+'</p>':'')+
   (expired?'<p class="info-strip">草案已过期，价格已撤下，请手动刷新；未自动挂单。</p>':'')+(payload&&payload.status==='PENDING_UNIT_REVIEW'?'<p class="info-strip">跨期股数与公司行动证据待核验，暂不生成续单。可稍后再次检查剩余目标。</p>':'')+(p?'<p><strong>'+esc(p.security.ticker)+'</strong> · '+p.quantity+' 股 · 模拟限价 $'+money(p.limit_price)+' · 占用 $'+money(p.notional)+' · 余款 $'+money(p.residual_cash)+'</p><p>采纳截止 '+esc(bj(p.accept_before))+'；报价截止 '+esc(bj(p.reference_valid_until))+'</p><button class="btn" data-action="accept" '+(busy||retry||p.quantity===0||clock.now()>=deadline()?'disabled':'')+'>'+ (p.proposal_kind==='CONTINUATION'?'模拟续单':'模拟挂单')+'</button>'+(p.proposal_kind==='CONTINUATION'?'<p>冻结目标 '+p.target_quantity+' 股 · 已持有 '+p.held_quantity+' 股 · 可用现金 $'+money(p.available_cash)+'</p>':'')+(p.quantity===0?'<p>'+(p.action==='NO_ACTION'?'已达到目标，无需续单。':'现金不足一股，无模拟单。')+'</p>':'')+(clock.now()>=deadline()?'<p>草案已过期，请手动刷新；未自动挂单。</p>':''):'')+
   (a?'<p>'+esc(a.security.ticker)+' · 已录 '+a.filled_quantity+' / '+a.order.quantity+' 股 · 封存限价 $'+money(a.order.limit)+' · '+(a.filled_quantity===a.order.quantity?'已全部成交':a.closed?'已关闭':'模拟单开放')+'</p><p>累计持有 '+Number(a.shares[a.security.security_id]||0)+' 股 · 现金 $'+money(a.cash)+' · 预留 $'+money(a.reserved_cash)+' · 已录费用 $'+money(a.fees)+'</p>'+(!a.closed&&a.filled_quantity<a.order.quantity?'<div><label>成交数量 <input name="quantity" type="number" min="1" step="1"></label><label>成交价 <input name="price"></label><label>费用（必填） <input name="fees"></label><label>发生时间（北京时间） <input name="eventTime" type="datetime-local" step="1"></label><button data-action="fill">记录模拟成交</button><button data-action="cancel">取消模拟单</button><button data-action="expire">确认已收盘到期</button></div>':''):'')+
   (a&&(a.closed||a.filled_quantity===a.order.quantity)?'<button class="btn btn-small" data-action="continue">检查剩余目标</button>':'')+'<button class="btn btn-small" data-action="read">'+(a?'恢复账户':'手动刷新草案')+'</button>'+(retry?'<button class="btn btn-small" data-action="retry">重试同一操作</button>':'');
  body.querySelectorAll('[data-action]').forEach(b=>{if(busy||(retry&& !['read','retry'].includes(b.dataset.action))||(b.dataset.action==='expire'&&a&&clock.now()<Date.parse(a.order.session_close)))b.disabled=true;b.addEventListener('click',()=>action(b.dataset.action));});
  for(const [k,v] of Object.entries(draft)){const el=body.querySelector('[name="'+k+'"]');if(el)el.value=v;}
 }
 async function request(path,data,mutation=false){
  if(!research||busy||!details.open||!parentOpen)return;busy=true;error='';const token=generation;controller=new AbortController();if(mutation)retry={path,data};else if(payload&&payload.proposal)payload=payload.account?{...payload,status:'ACCOUNT',proposal:null}:null;render();
  try{const r=await fetcher('/api/research_paper/intraday_paper/'+path,{method:data===undefined?'GET':'POST',cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json'},...(data===undefined?{}:{body:JSON.stringify(data)})});const d=await r.json();if(token!==generation||!details.open)return;if(!r.ok)throw Error(serverMessage(d.message));payload=validate(d);retry=null;
   if(expiry)clock.clear(expiry);if(payload.proposal)expiry=clock.set(()=>{if(token===generation)render();},Math.max(0,deadline()-clock.now()));
  }catch(e){if(token!==generation)return;error=e.message||'请求失败';if(!mutation){if(payload&&payload.account)payload={...payload,status:'ACCOUNT',proposal:null};else payload=null;}}
  finally{if(token===generation){busy=false;render();}}
 }
 function action(name){
  if(busy||!research)return;
  if(name==='read'){retry=null;return request(payload&&payload.account?'account?research_id='+encodeURIComponent(research.research_id):'preview',payload&&payload.account?undefined:{research_id:research.research_id});}
  if(name==='retry'&&retry)return request(retry.path,retry.data,true);
  if(retry)return;
  if(name==='continue'&&payload&&payload.account&&(payload.account.closed||payload.account.filled_quantity===payload.account.order.quantity))return request('continuation/preview',{research_id:research.research_id});
  if(name==='accept'){if(!payload||!payload.proposal||payload.proposal.quantity===0||clock.now()>=deadline())return;const continuation=payload.proposal.proposal_kind==='CONTINUATION';return request(continuation?'continuation/accept':'accept',{research_id:research.research_id,proposal_id:payload.proposal.proposal_id,operation_id:uuid(),...(continuation?{expected_revision:payload.account.revision}:{})},true);}
  if(!payload||!payload.account||payload.account.closed||payload.account.filled_quantity===payload.account.order.quantity)return;
  const a=payload.account,event={event_id:uuid(),kind:name.toUpperCase(),expected_revision:a.revision,order_id:a.order.order_id};
  try{
   const val=k=>body.querySelector('[name="'+k+'"]').value.trim();
   if(name==='fill'){const quantity=Number(val('quantity'));if(!Number.isSafeInteger(quantity)||quantity<=0||quantity>a.order.quantity-a.filled_quantity)throw Error('成交股数无效');const price=val('price'),fees=val('fees');money(price);money(fees);if(Number(price)<=0)throw Error('成交价须为正数');Object.assign(event,{quantity,price,fees,executed_at:beijingInput(val('eventTime'))});}
   else if(name==='cancel')event.cancelled_at=beijingInput(val('eventTime'));else if(name!=='expire'||clock.now()<Date.parse(a.order.session_close))return;
   return request('event',{research_id:research.research_id,event},true);
  }catch(e){error=e.message;render();}
 }
 function invalidate(){stop();research=null;draft={};body.innerHTML='';render();}
 function setResearch(data){stop();research=data;draft={};body.innerHTML='';render();if(details.open&&parentOpen)action('read');}
 details.addEventListener('toggle',()=>{onOpen(details.open);if(!details.open){stop();render();}else if(research&&parentOpen)action('read');});
 render();return {invalidate,setResearch,setParentOpen(value){parentOpen=value;if(!value){stop();render();}},suspend(){stop();render();},isOpen:()=>details.open};
}
if(typeof module!=='undefined'&&module.exports)module.exports={create,money,instant,beijingInput};root.ResearchIntradayPaper={create};
})(typeof window!=='undefined'?window:globalThis);
