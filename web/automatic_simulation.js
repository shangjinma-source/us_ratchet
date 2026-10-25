(function(root){
'use strict';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function money(value){
 const parts=String(value).split('/');const n=Number(parts[0]),d=parts.length===2?Number(parts[1]):1;
 if(parts.length>2||!Number.isFinite(n)||!Number.isFinite(d)||d<=0||n<0)throw Error('Invalid amount');
 return (n/d).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
}
function renderLegacy(data){
 if(data.simulation_only!==true||data.real_account!==false)throw Error('Invalid simulation');
 if(data.status==='WAITING_FOR_INITIALIZATION')return {title:'旧版本模拟 · 等待首次运行',html:'<p>独立模拟本金 $'+money(data.initial_cash)+'。尚未建立账户；美东交易日 10:00 取得有效数据后才开始。</p>'};
 if(data.status==='INITIALIZATION_REQUIRES_REVIEW')return {title:'旧版本模拟 · 首次运行待核查',html:'<p>已记录初始化尝试，但尚无可读取账户。需核查运行结果后恢复，不能当作已成交。</p>'};
 if(data.status!=='AVAILABLE')throw Error('Unavailable');
 const dailyLabels={NO_DECISION_RECORD:'尚未见当日决策记录',LATE_NO_NEW_DECISION:'错过决策时间，当日未生成新单',DECISION_STEP_COMPLETE:'当日决策步骤已完成',INITIAL_ORDERS_ACCEPTED:'首次模拟单已接受'};
 if(!data.daily||!dailyLabels[data.daily.decision_status])throw Error('Invalid daily status');
 const states={FILLED:'模拟已成交',CANCELLED:'已撤销',EXPIRED:'已到期',AWAITING_VERIFICATION:'已过有效期 · 待核验',MODEL_ORDER_OPEN:'读取时在有效期内'};
 let html='<p>本月目标 '+esc(data.target_month)+' · 模拟现金 $'+money(data.cash)+' · 挂单占用 $'+money(data.reserved_cash)+'</p>';
 html+='<p>纽约日期 '+esc(data.daily.session)+' · '+dailyLabels[data.daily.decision_status]+'</p>';
 if(data.daily.unresolved_order_results)html+='<p role="status">'+esc(data.daily.unresolved_order_results)+' 笔模拟单因数据不足仍无法判断成交；不能记作已成交或未成交。</p>';
 html+='<p>模拟持仓：'+(data.holdings.map(x=>esc(x.ticker)+' '+esc(x.shares)+' 股').join('、')||'无')+'</p>';
 html+='<p>目标持仓：'+(data.targets.map(x=>esc(x.ticker)+' '+esc(x.shares)+' 股').join('、')||'无')+'</p>';
 if(data.pending_operations.length)html+='<p role="status">存在未完成的模拟步骤，待核查；下列仅为已保存记录。</p>';
 if(data.orders.length){
  html+='<div style="overflow-x:auto"><table><thead><tr><th>股票</th><th>方向</th><th>限价 USD</th><th>未成交股数</th><th>状态</th><th>有效至（北京时间）</th></tr></thead><tbody>';
  for(const o of data.orders){
   if(!['BUY','SELL'].includes(o.side)||!states[o.display_status])throw Error('Invalid order');
   const end=new Date(o.session_close);if(!Number.isFinite(end.getTime()))throw Error('Invalid date');
   html+='<tr><td>'+esc(o.ticker)+'</td><td>'+ (o.side==='BUY'?'买入':'卖出')+'</td><td>$'+money(o.limit_price)+'</td><td>'+esc(o.quantity-o.filled_quantity)+'</td><td>'+states[o.display_status]+'</td><td>'+esc(end.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))+'</td></tr>';
  }
  html+='</tbody></table></div>';
 }else html+='<p>当前账本没有订单记录；这不代表今日已运行。</p>';
 html+='<p class="preview-caption">这是自动模拟的已保存记录，不是当前实盘挂单建议；不会向券商下单。页面不会持续刷新，已过有效期的限价请勿照挂。</p>';
 return {title:'旧版本模拟 · '+(data.pending_operations.length||data.daily.unresolved_order_results?'待核查':'已建立账户'),html};
}
function render(data){
 const view=renderLegacy(data);
 return {...view,html:'<p class="preview-caption">旧版独立模拟，未接入今日建议的50%仓位上限和20%退出规则。</p>'+view.html};
}
function mount(){
 const body=document.getElementById('automaticSimulationBody'),title=document.getElementById('automaticSimulationTitle'),button=document.getElementById('automaticSimulationRefresh');
 if(!body||!title||!button)return;
 async function refresh(){
  button.disabled=true;body.textContent='正在读取模拟记录…';
  try{const response=await fetch('/api/current_portfolio_research/automatic_simulation',{cache:'no-store'});if(!response.ok)throw Error('HTTP');const view=render(await response.json());title.textContent=view.title;body.innerHTML=view.html;}
  catch(error){title.textContent='旧版本模拟 · 暂不可读取';body.textContent='未能核验自动模拟状态，请稍后刷新。这里不会用旧记录替代当前结果。';}
  finally{button.disabled=false;}
 }
 button.addEventListener('click',refresh);refresh();
}
root.AutomaticSimulation={render};
if(typeof document!=='undefined')mount();
})(typeof window!=='undefined'?window:globalThis);
