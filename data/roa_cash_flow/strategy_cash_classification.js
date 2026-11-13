(function(root){'use strict';
function dollars(value){const parts=String(value).split('/');const n=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return Number.isFinite(n)?n.toFixed(2):'待核对'}
function unresolvedSummary(rows){
 let numerator=0n,denominator=1n;
 for(const row of rows){
  const value=String(row.unexplained_net_change);let n,d;
  if(/^-?\d+\/[1-9]\d*$/.test(value)){[n,d]=value.split('/').map(BigInt);}
  else if(/^-?\d+(?:\.\d+)?$/.test(value)){const [integer,fraction='']=value.split('.');n=BigInt(integer+fraction);d=10n**BigInt(fraction.length);}
  else return rows.length+' 笔资金差额待核对，合计待核验';
  numerator=numerator*d+n*denominator;denominator*=d;
 }
 return rows.length+' 笔资金差额待核对，合计 $'+dollars(String(numerator)+'/'+String(denominator))+'；不是已确认费用或盈亏';
}
function signedAmount(kind,value,direction){if(!/^\d+(\.\d{1,2})?$/.test(value)||Number(value)<=0)throw Error('请输入正数金额，最多两位小数');return (['WITHDRAWAL','FEE'].includes(kind)||(['CORRECTION','UNRECORDED_TRADE'].includes(kind)&&direction==='decrease')?'-':'')+value}
function reconciliationBody(review,links,classifications){return {event_id:'reconcile-'+crypto.randomUUID(),expected_revision:review.reconciliation_revision,document:{schema:'TRANSFER_RECONCILIATION_V1',account_id:review.account_id,account_revision:review.account_revision,transfer_revision:review.transfer_revision,links,classifications}}}
function mount({container,request=async(path,body)=>{const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const value=await r.json();if(!r.ok)throw Error(value.reason||'资金核对暂不可用');return value;}}){
 const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
 const summary=node('p'),panel=node('section'),description=node('p'),items=node('div'),add=node('button','增加一项'),save=node('button','保存原因'),recheck=node('button','按最新账户核对'),message=node('p');
 const cancel=node('button','取消修正');cancel.hidden=true;panel.append(description,items,add,save,recheck,cancel);const history=node('details');container.replaceChildren(summary,panel,message,history);panel.hidden=true;recheck.hidden=true;
 let editingId=null;const chosen=()=>editingId?current?.classified?.find(r=>r.event_id===editingId):current?.unresolved?.[0];
 let current=null,generation=0,busy=false,disposed=false,dirty=false,stale=false,profitPending=false,profitEpoch=0,expiryTimer=null;const attempted=new Set();const retryProfit=node('button','重试盈亏');retryProfit.hidden=true;container.append(retryProfit);summary.textContent='正在读取资金记录…';
 const binding=v=>JSON.stringify([v?.account_id,v?.revision,v?.classifications_sha256]);
 const transfers=node('details');transfers.hidden=true;container.append(transfers);let transferBinding=null,transferDirty=false;
 function renderTransfers(value){
  const review=value.transfer_review;transfers.hidden=!review;
  if(!review){transferBinding=null;transferDirty=false;return;}
  const key=binding(value);if(transferBinding===key&&transferDirty)return;
  transferBinding=key;transferDirty=false;transfers.replaceChildren(node('summary','内部转账与现金核对'));
  transfers.append(node('p','请选择每笔转账对应哪次现金更新。更改对应关系后，该项资金原因需重新确认；不会修改现金或发起转账。'));
  const selectors=[];
  for(const event of review.transfer_events){
   if(Date.parse(event.occurred_at)<=Date.parse(review.baseline_at))continue;
   const line=node('label',(event.kind==='SENT'?'转出':'到账')+' $'+dollars(event.principal??event.amount)+' · '+new Date(event.occurred_at).toLocaleString()+' '),select=node('select'),empty=node('option','暂未对应');empty.value='';select.append(empty);
   let previous=Date.parse(review.baseline_at);
   for(const row of review.confirmations){const at=Date.parse(review.confirmation_times[row.event_id]);if(Date.parse(event.occurred_at)>previous&&Date.parse(event.occurred_at)<=at){const option=node('option',new Date(at).toLocaleString()+' · 差额 $'+dollars(row.unexplained_net_change));option.value=row.event_id;select.append(option)}previous=at;}
   select.value=Object.keys(review.document?.links||{}).find(id=>review.document.links[id].includes(event.event_id))||'';select.onchange=()=>{transferDirty=true};line.append(select);transfers.append(line);selectors.push([event.event_id,select]);
  }
  const confirm=node('button','保存转账对应关系'),notice=node('p');transfers.append(confirm,notice);
  confirm.onclick=async()=>{if(busy||disposed)return;if(binding(current)!==key){notice.textContent='账户已变化，请刷新后重新核对';return;}
   const links={};for(const [id,select]of selectors){if(select.value)(links[select.value]??=[]).push(id)}
   const classifications={...review.document?.classifications};for(const id of Object.keys(classifications)){if(JSON.stringify(links[id]||[])!==JSON.stringify(review.document?.links[id]||[]))delete classifications[id]}
   busy=true;confirm.disabled=true;clearProfit();try{await request('/api/strategy-account/transfer-reconciliation',reconciliationBody(review,links,classifications));transferDirty=false;dirty=false;editingId=null;message.textContent='转账对应关系已保存，请继续核对剩余差额'}catch(e){message.textContent='保存结果待核对，请刷新确认：'+e.message}finally{busy=false;if(!disposed){transferDirty=false;await refresh()}}
  };
 }
 function clearProfit(){++profitEpoch;if(expiryTimer)clearTimeout(expiryTimer);if(current)current.profit=null;retryProfit.hidden=true;summary.textContent='正在核对最新资金记录…'}
 async function loadProfit(){if(disposed||profitPending||!current||current.profit||current.performance_reason!=='VALUATION_PENDING')return;const key=binding(current);if(attempted.has(key)){retryProfit.hidden=false;return;}attempted.add(key);profitPending=true;const epoch=profitEpoch;summary.textContent='资金记录已读取，正在计算盈亏…';retryProfit.hidden=true;try{const value=await request('/api/strategy-account/cash-classification/profit');if(disposed||epoch!==profitEpoch||key!==binding(current)||key!==binding(value))return;const until=Date.parse(value.profit_valid_until);if(!value.profit||!Number.isFinite(until)||until<=Date.now())throw Error(value.performance_reason||'等待有效行情');current.profit=value.profit;current.profit_valid_until=value.profit_valid_until;summary.textContent='净入金 $'+dollars(value.profit.net_external_flow)+' · 金额盈亏 $'+dollars(value.profit.profit_amount)+'（收益率、回撤待认证）';expiryTimer=setTimeout(()=>{if(!disposed&&key===binding(current)){current.profit=null;summary.textContent='盈亏报价已过期，请重试';retryProfit.hidden=false}},until-Date.now());}catch(e){if(!disposed&&epoch===profitEpoch&&key===binding(current)){current.profit=null;summary.textContent='资金记录已读取，盈亏暂不可用';retryProfit.hidden=false;}}finally{profitPending=false;if(!disposed&&current?.performance_reason==='VALUATION_PENDING'&&!current.profit){if(!attempted.has(binding(current)))loadProfit();else retryProfit.hidden=false;}}}
 retryProfit.onclick=()=>{if(current){attempted.delete(binding(current));loadProfit()}};
 function addItem(existing){const row=node('div'),kind=node('select');for(const [value,label]of [['DEPOSIT','入金'],['WITHDRAWAL','出金'],['INCOME','股息/利息'],['FEE','费用'],['CORRECTION','余额修正'],['UNRECORDED_TRADE','未录成交']]){const o=node('option',label);o.value=value;kind.append(o)}
 const amount=node('input'),at=node('input'),direction=node('select'),remove=node('button','删除');amount.placeholder='金额 USD（正数）';amount.inputMode='decimal';at.type='datetime-local';at.step='1';at.title='实际发生时间（本地时区 '+Intl.DateTimeFormat().resolvedOptions().timeZone+'）';
 for(const [v,t]of [['increase','增加'],['decrease','减少']]){const o=node('option',t);o.value=v;direction.append(o)}direction.hidden=true;kind.onchange=()=>{direction.hidden=!['CORRECTION','UNRECORDED_TRADE'].includes(kind.value);dirty=true};remove.onclick=()=>{row.remove();dirty=true};for(const input of [amount,at,direction])input.oninput=()=>dirty=true;
 row.append(kind,amount,at,direction,remove);items.append(row);if(existing){kind.value=existing.kind;direction.hidden=!['CORRECTION','UNRECORDED_TRADE'].includes(kind.value);const signed=Number(String(existing.amount).split('/')[0])/Number(String(existing.amount).split('/')[1]||1);amount.value=Math.abs(signed).toFixed(2);direction.value=signed<0?'decrease':'increase';const date=new Date(existing.effective_at);at.value=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,19)}}
 async function refresh({acceptNew=false}={}){if(busy||disposed)return;const token=++generation;try{const value=await request('/api/strategy-account/cash-classification');if(disposed||token!==generation)return;
 const old=current;if(old&&binding(old)===binding(value)&&old.profit&&Date.parse(old.profit_valid_until)>Date.now()){value.profit=old.profit;value.profit_valid_until=old.profit_valid_until;}if(old&&binding(old)!==binding(value))clearProfit();const classificationChanged=editingId&&old?.classified?.find(r=>r.event_id===editingId)?.document_sha256!==value.classified?.find(r=>r.event_id===editingId)?.document_sha256;current=value;renderTransfers(value);history.replaceChildren(node('summary','已记录资金原因'));for(const record of value.classified||[]){const line=node('div','确认 '+(record.received_at?new Date(record.received_at).toLocaleString():'时间待核对')+' · $'+dollars(record.unexplained_net_change)+' · '+(record.classification_state==='REPAIR_REQUIRED'?'此项仍需核对账户事实。':'已记录资金原因。')),edit=node('button','修正原因');edit.onclick=()=>{editingId=record.event_id;dirty=false;refresh({acceptNew:true})};line.append(edit);history.append(line)}const p=value.profit;summary.textContent=p?'净入金 $'+dollars(p.net_external_flow)+' · 金额盈亏 $'+dollars(p.profit_amount)+'（收益率、回撤待认证）':(['INCOMPLETE_MARK_DOMAIN','VALUATION_UNAVAILABLE','OUTSIDE_REGULAR_SESSION'].includes(value.performance_reason)?'等待有效行情后计算盈亏':value.unresolved?.length?unresolvedSummary(value.unresolved):'阶段金额盈亏待核对；未计为收益。');
 if(dirty&&old&&(binding(old)!==binding(value)||classificationChanged)&&!acceptNew){stale=true;save.disabled=true;recheck.hidden=false;message.textContent='账户已变化，已保留填写内容，请按最新账户核对后再保存。';return}
 if(acceptNew){if(editingId)dirty=false;stale=false;save.disabled=false;recheck.hidden=true;message.textContent='已更新差额，请核对填写内容再保存。'}
 cancel.hidden=!editingId;const selected=chosen();panel.hidden=!selected;if(!panel.hidden){description.textContent=(editingId?'修正已记录原因。差额 $':'当前核对第 1 / '+current.unresolved.length+' 笔（并非总差额）$')+dollars(selected.unexplained_net_change)+'，请补充实际原因和发生时间（本地时区 '+Intl.DateTimeFormat().resolvedOptions().timeZone+'）。';if(!dirty){items.replaceChildren();if(selected.document)selected.document.items.forEach(addItem);else addItem()}}
 loadProfit();
 }catch(e){if(!disposed&&token===generation){current=null;stale=true;save.disabled=true;recheck.hidden=false;summary.textContent='阶段金额盈亏待核验';message.textContent='资金核对暂不可用，已保留填写内容。'+e.message}}}
 cancel.onclick=()=>{editingId=null;dirty=false;stale=false;refresh({acceptNew:true})};add.onclick=()=>{addItem();dirty=true};recheck.onclick=()=>refresh({acceptNew:true});save.onclick=async()=>{if(busy||disposed||stale||!chosen())return;let documentValue;
 try{const r=chosen();const values=[...items.children].map((row,i)=>{const local=row.children[2].value;if(!local)throw Error('请填写实际发生时间');const at=new Date(local);if(!Number.isFinite(at.getTime()))throw Error('发生时间无效');return {item_id:String(i),kind:row.children[0].value,amount:signedAmount(row.children[0].value,row.children[1].value,row.children[3].value),effective_at:at.toISOString()}});if(!values.length)throw Error('请至少填写一项');documentValue={schema:'CASH_CHANGE_CLASSIFICATION_V1',account_id:current.account_id,cash_event_id:r.event_id,before_revision:r.before_revision,after_revision:r.after_revision,net_change:r.unexplained_net_change,items:values}}catch(e){message.textContent=e.message;return}
 clearProfit();busy=true;save.disabled=true;try{const payload={expected_revision:current.revision,document:documentValue};if(chosen().document_sha256)payload.expected_document_sha256=chosen().document_sha256;if(current.transfer_review){const review=current.transfer_review;if(review.status!=='SAVED_REQUIRES_VALUATION')throw Error('请先保存最新转账对应关系');await request('/api/strategy-account/transfer-reconciliation',reconciliationBody(review,review.document.links,{...review.document.classifications,[documentValue.cash_event_id]:documentValue}));}else await request('/api/strategy-account/cash-classification',payload);if(!disposed){dirty=false;editingId=null;message.textContent='原因已保存'}}catch(e){if(!disposed)message.textContent=e.message}finally{busy=false;if(!disposed){save.disabled=stale;await refresh()}}};
 const onAccount=()=>{clearProfit();refresh()};root.addEventListener?.('strategy-account-updated',onAccount);refresh();return{refresh,dispose(){disposed=true;++generation;++profitEpoch;if(expiryTimer)clearTimeout(expiryTimer);current=null;root.removeEventListener?.('strategy-account-updated',onAccount)}};
}
const api={mount,dollars,signedAmount,unresolvedSummary,reconciliationBody};root.StrategyCashClassification=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
