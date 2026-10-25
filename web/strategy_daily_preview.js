(function(root){
'use strict';
const labels={WAIT_POLICY_RELEASE:'等待策略启用',WAIT_SIGNAL:'等待有效信号',WAIT_MONTHLY_TARGET:'等待本月目标',DAILY_PREVIEW_DISABLED:'每日信号暂未启用',HOLD:'持有，今日无需操作',CONDITIONAL_PREVIEW_READY:'今日条件买卖建议'};
Object.assign(labels,{WAIT_FRESH_SIGNAL:'等待最新有效信号',WAIT_PENDING_RECONCILIATION:'等待挂单核对',WAIT_EXECUTION_ELIGIBILITY:'等待执行条件满足'});
function presentation(value,binding){
 if(!value||value.account_revision!==binding.account_revision||value.target_id!==binding.target_id)throw new Error('DAILY_RESPONSE_BINDING_MISMATCH');
 if(!Object.hasOwn(labels,value.status))throw new Error('DAILY_STATUS_NOT_ADMITTED');
 const ready=value.status==='CONDITIONAL_PREVIEW_READY';
 if(!ready&&((value.new_orders||[]).length||Object.keys(value.reference_quotes||{}).length))throw new Error('WAIT_MUST_NOT_CONTAIN_EXECUTABLE_QUOTES');
 return {status:value.status,message:labels[value.status],rows:(value.daily_gate?.rows||[]).map(row=>({security_id:row.security_id,action:({HOLD:'持有',BUY:'条件买入',SELL:'条件卖出',WAIT:'等待'})[row.action]||'等待',reason:labels[row.reason]||labels[value.status]})),new_orders:ready?structuredClone(value.new_orders||[]):[],reference_quotes:ready?structuredClone(value.reference_quotes||{}):{},prior_quotes_are_historical:true};
}
function render(container,value,binding){
 let result;try{result=presentation(value,binding);}catch(error){const heading=container.ownerDocument.createElement('p');heading.textContent='本次建议不可用；下方如有旧价格，仅供历史参考。';container.prepend(heading);container.dataset.dailyState='unavailable';throw error;}
 container.replaceChildren();container.dataset.dailyState=value.status;
 const heading=container.ownerDocument.createElement('p');heading.textContent=result.message;container.appendChild(heading);
 for(const order of result.new_orders){const row=container.ownerDocument.createElement('p');row.textContent=(order.ticker||order.security_id)+' · '+(order.side==='BUY'?'买入':'卖出')+' '+order.quantity+' 股 · 限价 '+order.limit_price;container.appendChild(row);}
 return result;
}
const api={presentation,render};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyDailyPreview=api;
})(typeof window!=='undefined'?window:globalThis);
