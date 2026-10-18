(function(root){
'use strict';
const viewAPI=typeof module!=='undefined'&&module.exports?require('./current_research_intraday_multiorder.js'):root.ResearchIntradayMultiorder;
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const requireValue=(ok,message)=>{if(!ok)throw Error(message);};
const hash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
function f(x){requireValue(typeof x==='string'&&x.length<=100&&/^\d+(?:\.\d+)?(?:\/\d+)?$/.test(x),'金额格式无效');const[a,b='1']=x.split('/'),d=BigInt(b)*10n**BigInt((a.split('.')[1]||'').length);requireValue(d>0n,'金额分母无效');return[BigInt(a.replace('.','')),d];}
const add=(a,b)=>[a[0]*b[1]+b[0]*a[1],a[1]*b[1]],mul=(a,n)=>[a[0]*BigInt(n),a[1]],eq=(a,b)=>a[0]*b[1]===b[0]*a[1],le=(a,b)=>a[0]*b[1]<=b[0]*a[1];
function timestamp(x){requireValue(typeof x==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(x)&&Number.isFinite(Date.parse(x)),'报价时点无效');return Date.parse(x);}
function validateProposal(p,a,now){
 requireValue(p&&hash(p.proposal_id)&&p.account_id===a.account_id&&p.account_revision===a.revision&&p.target_month===a.target_month&&p.activated===false&&p.reference_deadline_is_order_expiry===false,'方案账户或版本不一致');
 const allowed=['proposal_id','account_id','account_revision','target_month','target_quantities','orders','wait_cash','actual_cash','reserved_buy_cash','unreserved_cash','reference_valid_until','proposed_at','action','reference_deadline_is_order_expiry','activated'];requireValue(Object.keys(p).every(k=>allowed.includes(k)),'方案包含非精简字段');
 requireValue(a.orders.every(o=>o.closed)&&eq(f(a.reserved_cash),[0n,1n])&&a.positions.every(x=>x.reserved_quantity===0),'旧订单仍占用资源');
 requireValue(Array.isArray(p.orders)&&Array.isArray(p.wait_cash)&&p.target_quantities&&typeof p.target_quantities==='object'&&!Array.isArray(p.target_quantities),'目标格式无效');
 const positions=new Map(a.positions.map(x=>[x.security_id,x]));
 for(const [sid,q]of Object.entries(p.target_quantities))requireValue(positions.has(sid)&&Number.isSafeInteger(q)&&q>=0&&q===positions.get(sid).target_quantity,'冻结目标已变化');
 for(const [sid,x]of positions)requireValue((p.target_quantities[sid]||0)===x.target_quantity,'冻结目标遗漏');
 requireValue(eq(f(p.actual_cash),f(a.cash))&&eq(add(f(p.reserved_buy_cash),f(p.unreserved_cash)),f(a.cash)),'方案现金不守恒');
 let reserve=[0n,1n];const quantities=new Map();
 for(const o of p.orders){const x=positions.get(o.security_id);requireValue(x&&o.ticker===x.ticker&&['BUY','SELL'].includes(o.side)&&Number.isSafeInteger(o.quantity)&&o.quantity>0&&!quantities.has(o.security_id)&&Object.keys(o).every(k=>['security_id','ticker','side','quantity','limit_price'].includes(k)),'方案订单身份无效');const delta=x.target_quantity-x.quantity;requireValue(o.side===(delta>0?'BUY':'SELL')&&o.quantity<=Math.abs(delta)&&f(o.limit_price)[0]>0n,'方案差额或限价无效');if(o.side==='SELL')requireValue(o.quantity===-delta,'卖单未覆盖差额');else reserve=add(reserve,mul(f(o.limit_price),o.quantity));quantities.set(o.security_id,o.quantity);}
 requireValue(eq(reserve,f(p.reserved_buy_cash))&&le(reserve,f(a.cash)),'买单借用了未成交卖款');
 const waits=new Map();for(const w of p.wait_cash){const x=positions.get(w.security_id);requireValue(x&&!waits.has(w.security_id)&&w.reason==='WAIT_CASH'&&Number.isSafeInteger(w.remaining_deficit)&&w.remaining_deficit>0&&Object.keys(w).every(k=>['security_id','remaining_deficit','reason'].includes(k)),'待现金差额无效');waits.set(w.security_id,w.remaining_deficit);}
 for(const [sid,x]of positions){const delta=x.target_quantity-x.quantity;requireValue(delta>0?(quantities.get(sid)||0)+(waits.get(sid)||0)===delta:!waits.has(sid)&&(quantities.get(sid)||0)===-delta,'目标差额覆盖不完整');}
 requireValue(p.action===(p.orders.length?'PROPOSE_DIFFERENCES':p.wait_cash.length?'WAIT_CASH':'NO_ACTION'),'方案状态不一致');
 requireValue(timestamp(p.proposed_at)<=now,'方案时点在未来');
 if(p.reference_valid_until!==null)requireValue(timestamp(p.proposed_at)<timestamp(p.reference_valid_until)&&now<timestamp(p.reference_valid_until),'方案报价已过期');else requireValue(!p.orders.length&&!p.wait_cash.length&&a.positions.every(x=>x.quantity===0&&x.target_quantity===0),'缺少报价有效期');
 return structuredClone(p);
}
function create({controls,accountContainer,fetcher=root.fetch.bind(root),binding,clock={now:()=>Date.now(),set:(fn,ms)=>setTimeout(fn,ms),clear:id=>clearTimeout(id)},uuid=()=>crypto.randomUUID()}){
 const base='/api/research_paper/intraday_multiorder';binding=structuredClone(binding);
 let account=null,proposal=null,busy=false,generation=0,abort=null,timer=null,error='',retry=null,disabled=false;
 const component=viewAPI.create(accountContainer,{now:clock.now,uuid,onEvent:body=>request('event',body,true)});
 function clearProposal(){proposal=null;if(timer!==null)clock.clear(timer);timer=null;}
 function render(){if(proposal&&proposal.reference_valid_until&&clock.now()>=timestamp(proposal.reference_valid_until)){clearProposal();error='方案报价已过期，请重新预览；未自动挂单。';}
 controls.innerHTML='<p>同月目标差额模拟计划；不会自动撤单、续单或修改券商订单。</p>'+(error?'<p>'+esc(error)+'</p>':'')+'<button data-command="load" '+(busy||retry?'disabled':'')+'>读取模拟账户</button><button data-command="preview" '+(busy||retry||!account?'disabled':'')+'>预览剩余目标</button>'+(proposal?'<p>'+(proposal.action==='NO_ACTION'?'目标已达到，无需挂单。':proposal.action==='WAIT_CASH'?'现金不足，暂不生成新订单。':'待手动接受的模拟差额单')+'</p><p>可用现金 $'+viewAPI.money(proposal.actual_cash)+' · 买单预留 $'+viewAPI.money(proposal.reserved_buy_cash)+'</p>'+proposal.orders.map(o=>'<p>'+esc(o.ticker)+' '+(o.side==='BUY'?'买入':'卖出')+' '+o.quantity+' 股 · 新方案限价 $'+viewAPI.money(o.limit_price)+'</p>').join('')+(proposal.orders.length?'<button data-command="accept" '+(busy||retry?'disabled':'')+'>接受此纸面计划</button>':''):'')+(retry?'<button data-command="retry" '+(busy?'disabled':'')+'>重试同一操作</button>':'');controls.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>{const operations={load,preview,accept,retry:()=>request(retry.path,retry.body,true)};Promise.resolve().then(()=>operations[b.dataset.command]()).catch(()=>{});}));}
 function checkedAccount(d){requireValue(d&&d.research_only===true&&d.execution_blocked===true&&d.real_account===false,'返回口径不一致');const a=d.account;requireValue(a&&hash(a.revision),'账户版本缺失');return viewAPI.validate(a,{...binding,revision:a.revision});}
 async function request(path,body,mutation=false){
 if(disabled||busy)throw Error('请求正在处理或已失效');if(retry&&!mutation)throw Error('请先重试原操作确认结果');if(retry&&mutation)requireValue(path===retry.path&&JSON.stringify(body)===JSON.stringify(retry.body),'只能重试原操作');
 const token=generation,prior=account&&account.revision;busy=true;error='';clearProposal();abort=new AbortController();if(mutation)retry={path,body:structuredClone(body)};render();
 try{const response=await fetcher(base+'/'+path,{method:body===undefined?'GET':'POST',cache:'no-store',signal:abort.signal,headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});const d=await response.json();requireValue(token===generation&&!disabled,'响应已失效');if(!response.ok){const known=response.status===400&&d.mutation_outcome==='NOT_APPLIED';if(known)retry=null;throw Error(known?'方案已失效或账户版本变化，请读取账户后重新预览。':'结果暂未确认，请重试同一操作。');}const a=checkedAccount(d);
 const expected=path==='preview'?['CONTINUATION_PROPOSAL','NO_ACTION','WAIT_CASH']:path==='accept'?['ACCEPTED']:path==='event'?['RECORDED']:['ACCOUNT'];requireValue(expected.includes(d.status),'响应状态不一致');let p=null;if(path==='preview'){requireValue(prior===a.revision&&body.expected_revision===a.revision,'预览期间账户已变化');p=validateProposal(d.proposal,a,clock.now());requireValue(d.status===(p.orders.length?'CONTINUATION_PROPOSAL':p.action),'方案状态与响应不符');}else requireValue(d.proposal===null,'非预览响应不应携带新方案');
 account=a;proposal=p;retry=null;component.setAccount(account,{...binding,revision:account.revision});if(proposal&&proposal.reference_valid_until)timer=clock.set(()=>{if(token===generation)render();},Math.max(0,timestamp(proposal.reference_valid_until)-clock.now()));return d;
 }catch(e){if(token===generation){clearProposal();error=e.message||'请求未完成';}throw e;}finally{if(token===generation){busy=false;render();}}
 }
 function load(){return request('account?account_id='+encodeURIComponent(binding.account_id));}
 function preview(){requireValue(account&&!retry,'请先读取账户或处理未确认操作');return request('preview',{account_id:binding.account_id,expected_revision:account.revision});}
 function accept(){try{requireValue(proposal&&proposal.orders.length&&!retry,'没有可接受的新计划');validateProposal(proposal,account,clock.now());}catch(e){clearProposal();error=e.message;render();return Promise.reject(e);}return request('accept',{account_id:binding.account_id,proposal_id:proposal.proposal_id,operation_id:uuid(),expected_revision:account.revision},true);}
 function invalidate(){generation++;disabled=true;if(abort)abort.abort();clearProposal();account=null;retry=null;busy=false;error='';component.invalidate();render();}
 render();return{load,preview,accept,invalidate,retry(){requireValue(retry,'没有待重试操作');return request(retry.path,retry.body,true);}};
}
if(typeof module!=='undefined'&&module.exports)module.exports={create,validateProposal};root.ResearchIntradayMultiorderController={create,validateProposal};
})(typeof window!=='undefined'?window:globalThis);
