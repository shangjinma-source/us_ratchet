(function(root){
'use strict';
const common=typeof module!=='undefined'&&module.exports?require('./current_research_intraday_multiorder_controller.js'):root.ResearchIntradayMultiorderController;
const view=typeof module!=='undefined'&&module.exports?require('./current_research_intraday_multiorder.js'):root.ResearchIntradayMultiorder;
const requireValue=(ok,message)=>{if(!ok)throw Error(message);};
const hash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Binding is supplied by the host from a server-read, closed V1/V2 account and
// admitted security identities. It is never assembled from user price inputs.
function validateProposal(proposal,binding,now){
 requireValue(binding&&hash(binding.revision)&&hash(binding.original_acceptance_id)&&Array.isArray(binding.positions)&&Array.isArray(binding.securities),'缺少服务端账户绑定');
 const identities=new Map();
 for(const security of binding.securities){
  requireValue(security&&typeof security.security_id==='string'&&security.security_id&&typeof security.ticker==='string'&&security.ticker&&!identities.has(security.security_id),'证券身份无效');
  identities.set(security.security_id,security.ticker);
 }
 const held=new Map();
 for(const position of binding.positions){
  requireValue(position&&identities.get(position.security_id)===position.ticker&&!held.has(position.security_id)&&Number.isSafeInteger(position.quantity)&&position.quantity>=0,'持仓身份无效');
  held.set(position.security_id,position.quantity);
 }
 requireValue(proposal&&proposal.target_quantities&&Object.keys(proposal.target_quantities).every(sid=>identities.has(sid)),'目标证券不在服务端资格域');
 const domain=new Set([...held.keys(),...Object.keys(proposal.target_quantities)]);
 const account={account_id:binding.account_id,revision:binding.revision,target_month:binding.target_month,
  cash:binding.cash,reserved_cash:'0',orders:[],positions:Array.from(domain,sid=>({security_id:sid,ticker:identities.get(sid),quantity:held.get(sid)||0,reserved_quantity:0,target_quantity:proposal.target_quantities[sid]||0}))};
 view.money(proposal.selection_equity);view.money(proposal.sizing_equity);
 const normalized=structuredClone(proposal);
 delete normalized.selection_equity;delete normalized.sizing_equity;
 normalized.orders=normalized.orders.map(order=>{
  requireValue(Object.keys(order).every(key=>['security_id','side','quantity','limit_price'].includes(key)),'首次调仓订单字段无效');
  return {...order,ticker:identities.get(order.security_id)};
 });
 common.validateProposal(normalized,account,now);
 return structuredClone(proposal);
}

function createPendingStore(storage,key){
 requireValue(storage&&['getItem','setItem','removeItem'].every(name=>typeof storage[name]==='function')&&typeof key==='string'&&key.length>0,'缺少待确认操作存储');
 return {
  read(){const raw=storage.getItem(key);if(raw===null)return null;requireValue(typeof raw==='string'&&raw.length<=131072,'待确认记录过大');return JSON.parse(raw);},
  write(record){const raw=JSON.stringify(record);requireValue(raw.length<=131072,'待确认记录过大');const old=storage.getItem(key);requireValue(old===null||old===raw,'已有其他待确认操作');storage.setItem(key,raw);requireValue(storage.getItem(key)===raw,'待确认操作保存失败');},
  clear(record){const raw=JSON.stringify(record),old=storage.getItem(key);if(old===null)return;requireValue(old===raw,'待确认操作已变化');storage.removeItem(key);requireValue(storage.getItem(key)===null,'待确认操作清除失败');}
 };
}

function create({controls,binding,onAccepted,pendingStore,initialPreview=null,fetcher=root.fetch.bind(root),uuid=()=>crypto.randomUUID(),clock={now:()=>Date.now(),set:(fn,ms)=>setTimeout(fn,ms),clear:id=>clearTimeout(id)}}){
 requireValue(typeof onAccepted==='function','必须配置已接受账户的交接入口');
 requireValue(pendingStore&&['read','write','clear'].every(name=>typeof pendingStore[name]==='function'),'必须配置待确认操作存储');
 binding=structuredClone(binding);
 let proposal=null,retry=null,busy=false,disabled=false,completed=false,generation=0,timer=null,abort=null,error='';
 const base='/api/research_paper/intraday_initial_retarget';
 const saved=pendingStore.read();
 if(saved!==null){
  requireValue(saved&&saved.schema==='INITIAL_RETARGET_PENDING_V1'&&JSON.stringify(saved.binding)===JSON.stringify(binding),'待确认操作账户绑定不一致');
  const body=saved.body;
  requireValue(body&&Object.keys(body).sort().join(',')==='account_id,expected_revision,operation_id,proposal_id'&&body.account_id===binding.account_id&&body.expected_revision===binding.revision&&hash(body.proposal_id)&&typeof body.operation_id==='string'&&/^[A-Za-z0-9:_-]{1,160}$/.test(body.operation_id),'待确认请求无效');
  // Validate the original proposal at its original instant, only to restore
  // the exact already-sent request. Never display it as a current quote.
  validateProposal(saved.proposal,binding,Date.parse(saved.proposal.proposed_at));
  requireValue(saved.proposal.proposal_id===body.proposal_id&&saved.proposal.orders.length>0,'待确认方案不一致');
  retry=structuredClone(saved);error='发现未确认提交，请重试原操作核对结果；不展示旧报价。';
 }
 function clearProposal(){proposal=null;if(timer!==null)clock.clear(timer);timer=null;}
 function render(){
  if(proposal&&clock.now()>=Date.parse(proposal.reference_valid_until)){clearProposal();error='报价已过期，请重新预览。';}
  controls.innerHTML='<p>首次月度调仓 · 纸面模拟</p>'+(error?'<p>'+esc(error)+'</p>':'')+
   (completed?'<p>方案已接受，后续操作请进入模拟账户。</p>':'<button data-command="preview" '+(busy||retry||disabled?'disabled':'')+'>预览月度调仓</button>')+
   (proposal?'<p>当前现金 $'+view.money(proposal.actual_cash)+' · 买单预留 $'+view.money(proposal.reserved_buy_cash)+'；未成交卖款不计入可用现金。</p>'+proposal.orders.map(o=>'<p>'+esc(binding.securities.find(s=>s.security_id===o.security_id).ticker)+' '+(o.side==='BUY'?'买入':'卖出')+' '+o.quantity+' 股 · 限价 $'+view.money(o.limit_price)+'</p>').join('')+
    (proposal.wait_cash.length?'<p>部分买入需等待实际卖出成交后重新计算。</p>':'')+'<p>报价有效至 '+esc(proposal.reference_valid_until)+'</p>'+(proposal.orders.length?'<button data-command="accept" '+(busy||retry||disabled?'disabled':'')+'>接受此纸面调仓</button>':'<p>当前没有可接受的新订单。</p>'):'')+
   (retry?'<button data-command="retry" '+(busy||disabled?'disabled':'')+'>重试同一操作</button>':'');
  controls.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>Promise.resolve().then(()=>({preview,accept,retry:retryOperation})[button.dataset.command]()).catch(()=>{})));
 }
 function flags(data){requireValue(data&&data.research_only===true&&data.execution_blocked===true&&data.real_account===false&&data.scope==='FIRST_TOP1_MONTHLY_RETARGET_ONLY_NOT_GLOBAL_OPTIMUM','响应范围不一致');}
 function takePreview(data){
  flags(data);
  requireValue(['RETARGET_PROPOSAL','NO_ACTION','WAIT_CASH'].includes(data.status)&&data.account_id===binding.account_id&&data.expected_revision===binding.revision,'预览账户版本不一致');
  const checked=validateProposal(data.proposal,binding,clock.now());
  requireValue(data.status===(checked.orders.length?'RETARGET_PROPOSAL':checked.action),'方案响应状态不一致');
  proposal=checked;const token=generation;
  timer=clock.set(()=>{if(token===generation)render();},Math.max(0,Date.parse(proposal.reference_valid_until)-clock.now()));
 }
 function acceptedAccount(data,pending){
  flags(data);requireValue(data.status==='ACCEPTED'&&data.mutation_outcome==='APPLIED_OR_IDEMPOTENT','接受结果未确认');
  const account=data.account;
  const checked=view.validate(account,{account_id:binding.account_id,original_acceptance_id:binding.original_acceptance_id,target_month:binding.target_month,
   revision:account&&account.revision,retarget_acceptance_id:account&&account.retarget_acceptance_id});
  const expected=pending.proposal.target_quantities;
  requireValue(checked.positions.every(p=>binding.securities.some(s=>s.security_id===p.security_id&&s.ticker===p.ticker)),'接受后证券身份不一致');
  requireValue(checked.positions.every(p=>p.target_quantity===(expected[p.security_id]||0))&&Object.keys(expected).every(sid=>checked.positions.some(p=>p.security_id===sid&&p.target_quantity===expected[sid])),'接受后目标不一致');
  return checked;
 }
 async function request(path,body,mutation=false){
  requireValue(!disabled&&!completed&&!busy,'操作已失效或正在处理中');
  requireValue(!retry||(mutation&&JSON.stringify(body)===JSON.stringify(retry.body)),'请先确认原操作结果');
  const token=generation;busy=true;error='';clearProposal();abort=new AbortController();render();
  try{
   const response=await fetcher(base+'/'+path,{method:'POST',cache:'no-store',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   const data=await response.json();requireValue(token===generation&&!disabled,'响应已失效');
   if(!response.ok){
    if(mutation&&response.status===400&&data.mutation_outcome==='NOT_APPLIED'){pendingStore.clear(retry);retry=null;}
    throw Error(mutation&&retry?'结果未确认，请重试同一操作，不要另建调仓。':'未能生成有效方案，请刷新账户后重试。');
   }
   flags(data);
   if(!mutation){
    takePreview(data);
   }else{
    const account=acceptedAccount(data,retry);
    // Keep the successful receipt if host handoff throws: exact retry can
    // recover it without inventing another mutation identifier.
    await onAccepted(structuredClone(account));
    requireValue(token===generation&&!disabled,'账户交接已失效');
    pendingStore.clear(retry);retry=null;completed=true;
   }
   return data;
  }catch(errorValue){if(token===generation){clearProposal();error=errorValue.message||'请求未完成';}throw errorValue;}
  finally{if(token===generation){busy=false;render();}}
 }
 function preview(){return request('preview',{account_id:binding.account_id,expected_revision:binding.revision});}
 function accept(){
  try{requireValue(proposal&&proposal.orders.length&&!retry&&!busy&&!completed&&!disabled,'没有可接受的方案');validateProposal(proposal,binding,clock.now());}
  catch(errorValue){clearProposal();error=errorValue.message;render();return Promise.reject(errorValue);}
  const body={account_id:binding.account_id,expected_revision:binding.revision,proposal_id:proposal.proposal_id,operation_id:uuid()};
  const record={schema:'INITIAL_RETARGET_PENDING_V1',binding:structuredClone(binding),body:structuredClone(body),proposal:structuredClone(proposal)};
  try{requireValue(typeof body.operation_id==='string'&&/^[A-Za-z0-9:_-]{1,160}$/.test(body.operation_id),'操作编号无效');pendingStore.write(record);retry=record;}
  catch(errorValue){disabled=true;clearProposal();error='提交前记录保存失败，未发送请求；请恢复存储后重新加载。';render();return Promise.reject(errorValue);}
  return request('accept',body,true);
 }
 function retryOperation(){requireValue(retry,'没有待确认的操作');return request('accept',retry.body,true);}
 function invalidate(){generation++;disabled=true;if(abort)abort.abort();clearProposal();busy=false;error=retry?'原提交结果仍未确认；恢复此账户时须使用原操作编号。':'';render();}
 if(initialPreview&&!retry)takePreview(initialPreview);
 render();return{preview,accept,retry:retryOperation,invalidate,pendingRequest(){return retry?structuredClone(retry.body):null;}};
}
async function open({accountId,signal,...options}){
 requireValue(typeof accountId==='string'&&/^[A-Za-z0-9:_-]{1,160}$/.test(accountId),'账户编号无效');
 requireValue(options.pendingStore&&typeof options.onAccepted==='function','缺少恢复存储或账户交接');
 const active=()=>requireValue(!signal||!signal.aborted,'账户加载已取消');
 active();
 const saved=options.pendingStore.read();
 if(saved!==null){
  requireValue(saved.binding&&saved.binding.account_id===accountId,'待确认操作属于其他账户');
  return {kind:'INITIAL',controller:create({...options,binding:saved.binding})};
 }
 options.controls.innerHTML='<p>正在读取已验证的模拟账户…</p>';
 try{
  const fetcher=options.fetcher||root.fetch.bind(root);
  const response=await fetcher('/api/research_paper/intraday_initial_retarget/context?account_id='+encodeURIComponent(accountId),{method:'GET',cache:'no-store',signal});
  const data=await response.json();active();
  requireValue(response.ok&&data.research_only===true&&data.execution_blocked===true&&data.real_account===false,'账户或所需来源暂不可用');
  if(data.status==='MULTIORDER_CONTEXT'){
   requireValue(data.scope==='EXISTING_MULTIORDER_ACCOUNT','账户响应范围无效');
   const account=data.account;
   const checked=view.validate(account,{account_id:accountId,revision:account&&account.revision,original_acceptance_id:account&&account.original_acceptance_id,retarget_acceptance_id:account&&account.retarget_acceptance_id,target_month:account&&account.target_month});
   await options.onAccepted(checked);active();options.controls.innerHTML='<p>已恢复模拟账户。</p>';
   return {kind:'ACCOUNT',account:checked};
  }
  requireValue(data.status==='RETARGET_CONTEXT'&&data.scope==='FIRST_TOP1_MONTHLY_RETARGET_ONLY_NOT_GLOBAL_OPTIMUM'&&data.binding&&data.binding.account_id===accountId,'账户绑定返回不一致');
  return {kind:'INITIAL',controller:create({...options,binding:data.binding,initialPreview:data.preview})};
 }catch(errorValue){if(!signal||!signal.aborted)options.controls.innerHTML='<p>账户暂不可用，未生成新调仓。请检查账户和行情来源后重试。</p>';throw errorValue;}
}
if(typeof module!=='undefined'&&module.exports)module.exports={create,open,validateProposal,createPendingStore};root.ResearchIntradayInitialRetargetController={create,open,validateProposal,createPendingStore};
})(typeof window!=='undefined'?window:globalThis);
