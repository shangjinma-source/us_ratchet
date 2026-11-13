(function(root){'use strict';
const endpoint='/api/strategy-account/internal-transfers';
async function request(path,body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const response=await fetch(path,{method:body?'POST':'GET',cache:'no-store',signal:controller.signal,
  ...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  const value=await response.json();if(!response.ok)throw Error(value.status||'读取失败');return value;
 }finally{clearTimeout(timer)}
}
function mount({container,send=request,uuid=()=>crypto.randomUUID()}){
 const doc=container.ownerDocument||document,node=(tag,text)=>{const n=doc.createElement(tag);if(text)n.textContent=text;return n;};
 const panel=node('details'),title=node('summary','券商间转账记录'),status=node('p'),history=node('div');
 const form=node('form'),kind=node('select'),direction=node('select'),pending=node('select'),amount=node('input'),fee=node('input'),at=node('input');
 const save=node('button','记录已发生的转账'),refresh=node('button','刷新记录');save.type='submit';refresh.type='button';
 const option=(select,value,label)=>{const o=node('option',label);o.value=value;select.append(o)};
 option(kind,'SENT','已转出');option(kind,'RECEIVED','已到账');
 option(direction,'HSBC','汇丰 → 盈立');option(direction,'USMART','盈立 → 汇丰');
 amount.inputMode='decimal';fee.inputMode='decimal';fee.value='0';at.type='datetime-local';at.step='1';
 const field=(label,input)=>{const wrapper=node('label',label);wrapper.append(input);return wrapper};
 const sourceField=field('方向 ',direction),pendingField=field('对应转账 ',pending),feeField=field('另行扣除的费用 USD ',fee);
 form.append(field('状态 ',kind),sourceField,pendingField,field('本金 USD ',amount),feeField,field('实际发生时间（本机时区） ',at),save);
 panel.append(title,node('p','这里只记账，不发起银行转账。在途资金不可用于买入；到账后仍需更新实际购买力。'),status,history,form,refresh);
 container.replaceChildren(panel);
 let current=null,busy=false,attempt=null,disposed=false;
 function mode(){sourceField.hidden=feeField.hidden=kind.value!=='SENT';pendingField.hidden=kind.value!=='RECEIVED'}
 kind.onchange=mode;mode();
 function lock(value){busy=value;for(const n of [kind,direction,pending,amount,fee,at])n.disabled=value||!!attempt;save.disabled=refresh.disabled=value;save.textContent=attempt?'重试同一笔记录':'记录已发生的转账'}
 function render(value){
  current=value;history.replaceChildren();pending.replaceChildren();
  const transfers=Object.entries(value.summary.transfers);
  status.textContent='在途 $'+value.summary.in_transit_usd+' · 已记录费用 $'+value.summary.confirmed_fees_usd;
  if(!transfers.length)history.append(node('p','暂无转账记录'));
  for(const [id,row]of transfers){
   const names={HSBC:'汇丰',USMART:'盈立'};
   const label=names[row.source]+' → '+names[row.destination]+' · 本金 $'+row.principal;
   history.append(node('p',label+' · 已到账 $'+row.received+' · 在途 $'+row.in_transit+' · '+row.sent_at));
   if(row.status==='IN_TRANSIT')option(pending,id,label+' · 待到账 $'+row.in_transit);
  }
 }
 async function read(){
  const value=await send(endpoint);if(disposed)return;
  render(value);
  if(attempt){
   const found=value.state.events.find(e=>e.event_id===attempt.event.event_id);
   if(found&&Object.keys(found).length===Object.keys(attempt.event).length&&Object.keys(found).every(k=>found[k]===attempt.event[k])){attempt=null;amount.value='';at.value='';status.textContent+=' · 上次记录已保存';}
   else if(found){throw Error('EVENT_ID_CONFLICT')}
   else status.textContent+=' · 上次结果未确认；保存按钮将重试同一笔，请勿重新录入';
  }
 }
 async function reload(){if(busy||disposed)return;lock(true);try{await read()}catch(e){status.textContent='读取失败，请重试；当前记录未核验'}finally{lock(false)}}
 function exact(value,positive){if(!/^\d+(\.\d{1,2})?$/.test(value)||value.length>32||(positive&&!/[1-9]/.test(value)))throw Error('请输入正确的美元金额（最多两位小数）');return value}
 async function submit(event){
  event.preventDefault();if(busy||disposed)return;
  lock(true);
  try{
   if(!current)throw Error('请先刷新记录');
   if(!attempt){
    const date=new Date(at.value);if(!at.value||!Number.isFinite(date.getTime()))throw Error('请填写实际发生时间');
    const item={event_id:uuid(),transfer_id:kind.value==='SENT'?uuid():pending.value,kind:kind.value,occurred_at:date.toISOString()};
    if(kind.value==='SENT')Object.assign(item,{source:direction.value,destination:direction.value==='HSBC'?'USMART':'HSBC',principal:exact(amount.value,true),fee:exact(fee.value,false)});
    else{if(!item.transfer_id)throw Error('没有待到账的转账');item.amount=exact(amount.value,true)}
    attempt={expected_revision:current.state.revision,event:item};
   }
   try{
    const value=await send(endpoint,attempt);if(disposed)return;render(value);attempt=null;amount.value='';at.value='';status.textContent+=' · 已保存，购买力未修改';
   }catch(error){
    // A lost response may follow a successful commit. Read back before allowing another write.
    status.textContent='保存结果待确认，正在核对…';
    try{await read()}catch(e){status.textContent='保存结果待确认，请刷新记录；重试会使用同一笔编号'}
    if(attempt&&['STALE_REVISION','EVENT_ID_CONFLICT','VALID_OCCURRED_TIME_REQUIRED','RECEIPT_EXCEEDS_PENDING_PRINCIPAL','RECEIPT_BEFORE_TRANSFER','UNKNOWN_TRANSFER','TRANSFER_ALREADY_RECORDED'].includes(error.message)){attempt=null;status.textContent='未保存：'+error.message+'；请核对后修改'}
   }
  }catch(error){status.textContent=error.message}finally{lock(false)}
 }
 form.onsubmit=submit;refresh.onclick=reload;
 return {ready:reload(),reload,dispose(){disposed=true},elements:{panel,status,history,form,kind,direction,pending,amount,fee,at,save,refresh}};
}
const api={mount};if(typeof module==='object'&&module.exports)module.exports=api;else root.BrokerInternalTransfers=api;
})(typeof window==='undefined'?globalThis:window);
