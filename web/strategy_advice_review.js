(function(root){
'use strict';
const endpoint='/api/strategy-advice-v1/observations';
function money(value){
 const parts=String(value??'').split('/');
 if(parts.length>2||parts.some(x=>!x.trim()))return '—';
 const number=Number(parts[0])/(parts.length===2?Number(parts[1]):1);
 return Number.isFinite(number)&&number>0?'$'+number.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
}
function time(value){
 if(typeof value!=='string'||!/(Z|[+-]\d\d:\d\d)$/.test(value))return '时间未记录';
 const instant=new Date(value);
 return Number.isFinite(instant.getTime())?instant.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'时间未记录';
}
function rows(items){
 return items.flatMap(item=>{
  const state=item.final_return_status==='READY'?'曾生成建议 · 非当前指令':
   item.final_return_status==='HOLD'?'记录为持有 · 非当前指令':
   item.final_return_status==='WAIT'?'返回前已转为等待':
   item.final_return_status==='NOT_RECORDED'?'返回状态未记录':'返回状态未核实';
  return (item.new_orders?.length?item.new_orders:[null]).map(order=>({
   generated:time(item.generated_at),ticker:order?.ticker||order?.security_id||'—',
   side:order?({BUY:'买入',SELL:'卖出'}[order.side]||'方向未核实'):'无买卖建议',
   quantity:order&&Number.isSafeInteger(order.quantity)&&order.quantity>0?String(order.quantity):'—',
   price:order?money(order.limit_price):'—',state,executable:false,
   followup:item.followup_status==='NOT_ADMITTED'?'1 / 5 / 20 日：待接入':'1 / 5 / 20 日：无已核验数据'
  }));
 });
}
function mount(container,{fetchImpl=root.fetch.bind(root),onLegacy=()=>{}}={}){
 const doc=container.ownerDocument,el=(tag,text)=>{
  const node=doc.createElement(tag);if(text!==undefined)node.textContent=text;return node;
 };
 const heading=el('h3','新策略建议记录'),notice=el('p','历史生成建议，不代表成交，也不是当前可执行指令。');
 const controls=el('div'),refresh=el('button','刷新记录'),next=el('button','下一页'),legacy=el('button','旧策略历史记录');
 for(const button of [refresh,next,legacy]){button.type='button';button.className='btn';controls.appendChild(button);}
 const body=el('div');body.className='monthly-table-scroll';
 container.replaceChildren(heading,notice,controls,body);
 let disposed=false,busy=false,epoch=0,cursor=0,previousAfter=0;
 function message(text){body.replaceChildren(el('p',text));}
 async function load(after=0){
  if(disposed||busy)return;
  busy=true;refresh.disabled=next.disabled=true;const token=++epoch;
  message('正在读取记录…');
  try{
   const response=await fetchImpl(endpoint+'?after='+after+'&limit=20',{method:'GET',cache:'no-store'});
   if(disposed||token!==epoch)return;
   if(response.status===404){message('新策略复盘尚未启用。');return;}
   if(!response.ok)throw Error('AUDIT_UNAVAILABLE');
   const data=await response.json();
   if(disposed||token!==epoch)return;
   if(!Array.isArray(data.items)||data.items.length>20||!Number.isSafeInteger(data.next_cursor)||data.next_cursor<after||
      data.items.some(item=>!item||typeof item!=='object'||!Array.isArray(item.new_orders)||item.new_orders.length>250))
    throw Error('AUDIT_SCHEMA');
   cursor=data.next_cursor;previousAfter=after;
   if(!data.items.length){message('暂无已保存的新策略建议记录。');return;}
   const table=el('table'),head=el('tr');
   for(const label of ['生成时间（北京时间）','股票','方向','股数','当时限价 USD','记录状态'])head.appendChild(el('th',label));
   table.appendChild(head);
   for(const row of rows(data.items)){
    const tr=el('tr');
    for(const value of [row.generated,row.ticker,row.side,row.quantity,row.price,row.state]){
     tr.appendChild(el('td',value));
    }
    table.appendChild(tr);
   }
   body.replaceChildren(table);
   if(data.items.some(item=>item.new_orders.length))
    body.appendChild(el('p',data.items.filter(item=>item.new_orders.length).every(item=>item.followup_status==='NOT_ADMITTED')
     ?'买卖建议的 1 / 5 / 20 日价格跟踪：待接入。':'买卖建议的 1 / 5 / 20 日价格跟踪：暂无已核验数据。'));
   next.disabled=cursor<=after;
  }catch(_){if(!disposed&&token===epoch)message('建议记录暂不可用，请稍后刷新。');}
  finally{if(!disposed&&token===epoch){busy=false;refresh.disabled=false;}}
 }
 const reload=()=>load(0),more=()=>load(cursor),old=()=>onLegacy();
 refresh.addEventListener('click',reload);next.addEventListener('click',more);legacy.addEventListener('click',old);
 next.disabled=true;
 return {ready:load(0),refresh:reload,elements:{refresh,next,legacy,body},
  getState:()=>({busy,cursor,previousAfter}),
  dispose(){disposed=true;++epoch;refresh.removeEventListener('click',reload);next.removeEventListener('click',more);legacy.removeEventListener('click',old);}
 };
}
const api={mount,rows,money};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyAdviceReview=api;
})(typeof window!=='undefined'?window:globalThis);
