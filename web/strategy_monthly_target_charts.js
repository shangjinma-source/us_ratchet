(function(root){
'use strict';
function mount({container,fetchImpl=root.fetch.bind(root),createCharts=root.SelectedStockCharts.createSelectedStockCharts}){
 let charts=null,targetId=null,generation=0,fills=[],account=null,holdingRevision=null;
 function priceLabel(value){const parts=String(value??'').split('/'),number=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return parts.length<=2&&Number.isFinite(number)&&number>0?number.toLocaleString('en-US',{maximumFractionDigits:8}):'待核验';}
 function unconfigured(){
  if(targetId||holdingRevision)return;
  container.textContent='账户目标尚未配置，目标生成后展示对应 K 线。'+(fills.length?' 已录真实成交：'+fills.map(fill=>`${fill.ticker} ${fill.side==='BUY'?'买入':fill.side==='SELL'?'卖出':'方向待核验'} ${fill.quantity} 股 @ $${priceLabel(fill.price)} · ${fill.executed_at}`).join('；'):'');
 }
 function clear(){generation++;charts?.destroy();charts=null;targetId=null;holdingRevision=null;container.replaceChildren();}
 function showHoldings(){
  const stocks=(account?.holdings||[]).filter(row=>row.quantity>0);
  if(!account?.revision||!stocks.length){unconfigured();return;}
  holdingRevision=account.revision;const revision=holdingRevision,current=generation;
  charts=createCharts(container,async(ticker,interval,signal)=>{
   const stock=stocks.find(row=>row.ticker===ticker);if(!stock)throw Error('HOLDING_STOCK_REQUIRED');
   const query=new URLSearchParams({account_revision:revision,security_id:stock.security_id,interval});
   const response=await fetchImpl('/api/strategy-account/holding-bars?'+query,{signal,cache:'no-store'});
   if(!response.ok)throw Error('HOLDING_CHART_UNAVAILABLE');
   const data=await response.json();
   if(current!==generation||data.scope!=='RECORDED_HOLDING_HISTORY'||data.account_revision!==revision||data.security_id!==stock.security_id||data.ticker!==ticker)throw Error('HOLDING_CHART_CHANGED');
   return data;
  });
  charts.setSelection({recorded_holding:true,label:'已录真实持仓 · 历史 K 线（非今日报价） · 账户月度目标尚未配置',stocks:stocks.map(row=>({...row}))});
  charts.setFills?.(fills);
 }
 function setTarget(target){
  if(target?.target_id===targetId)return;
  clear();if(!target){showHoldings();return;}
  targetId=target.target_id;const current=generation;
  const stocks=target.targets.filter(row=>row.quantity>0);
  if(!stocks.length){container.textContent='本月目标为空仓，无入选股票 K 线。';return;}
  charts=createCharts(container,async(ticker,interval,signal)=>{
   const stock=stocks.find(row=>row.ticker===ticker);if(!stock)throw Error('TARGET_STOCK_REQUIRED');
   const query=new URLSearchParams({target_id:target.target_id,security_id:stock.security_id,interval});
   const response=await fetchImpl('/api/strategy-account/target/bars?'+query,{signal,cache:'no-store'});
   if(!response.ok)throw Error('TARGET_CHART_UNAVAILABLE');
   const data=await response.json();
   if(current!==generation||data.target_id!==target.target_id||data.security_id!==stock.security_id||data.ticker!==ticker)throw Error('TARGET_CHART_CHANGED');
   return data;
  });
  charts.setSelection({monthly_target:true,label:`本月目标 · 历史日线截至 ${target.historical_training_cutoff} · 非今日报价 · 红涨绿跌`,stocks:stocks.map(row=>({ticker:row.ticker,security_id:row.security_id,quantity:row.quantity}))});
  charts.setFills?.(fills);
 }
 return {setTarget,setAccount(value){const changed=account?.revision!==value?.revision;account=value?structuredClone(value):null;fills=Array.isArray(account?.fills)?account.fills.map(fill=>({...fill})):[];if(!targetId&&changed){clear();showHoldings();}else charts?.setFills?.(fills);},setFills(value){fills=Array.isArray(value)?value.map(fill=>({...fill})):[];charts?.setFills?.(fills);unconfigured();},destroy(){fills=[];account=null;clear();}};
}
const api={mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StrategyMonthlyTargetCharts=api;
})(typeof globalThis!=='undefined'?globalThis:this);
