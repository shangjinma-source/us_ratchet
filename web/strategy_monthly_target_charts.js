(function(root){
'use strict';
function mount({container,fetchImpl=root.fetch.bind(root),createCharts=root.SelectedStockCharts.createSelectedStockCharts,latestDisplayEnabled=false}){
 let charts=null,targetId=null,generation=0,fills=[],account=null,holdingRevision=null,savedTarget=null,selectionKey=null;
 function priceLabel(value){const parts=String(value??'').split('/'),number=Number(parts[0])/(parts.length===2?Number(parts[1]):1);return parts.length<=2&&Number.isFinite(number)&&number>0?number.toLocaleString('en-US',{maximumFractionDigits:8}):'待核验';}
 function unconfigured(){
  if(targetId||holdingRevision)return;
  container.textContent='账户目标尚未配置，目标生成后展示对应 K 线。'+(fills.length?' 已录真实成交：'+fills.map(fill=>`${fill.ticker} ${fill.side==='BUY'?'买入':fill.side==='SELL'?'卖出':'方向待核验'} ${fill.quantity} 股 @ $${priceLabel(fill.price)} · ${fill.executed_at}`).join('；'):'');
 }
 function clear(){generation++;charts?.destroy();charts=null;targetId=null;holdingRevision=null;selectionKey=null;container.replaceChildren();}
 function showHoldings(){
  const stocks=(account?.holdings||[]).filter(row=>row.quantity>0);
  if(!account?.revision||!stocks.length){unconfigured();return;}
  holdingRevision=account.revision;const revision=holdingRevision,current=generation;
  charts=createCharts(container,async(ticker,interval,signal)=>{
   const stock=stocks.find(row=>row.ticker===ticker);if(!stock)throw Error('HOLDING_STOCK_REQUIRED');
   if(latestDisplayEnabled){const value=await latest(ticker,stock,interval,signal,revision,null,current);if(value)return value;}
   const query=new URLSearchParams({account_revision:revision,security_id:stock.security_id,interval});
   const response=await fetchImpl('/api/strategy-account/holding-bars?'+query,{signal,cache:'no-store'});
   if(!response.ok)throw Error('HOLDING_CHART_UNAVAILABLE');
   const data=await response.json();
   if(current!==generation||data.scope!=='RECORDED_HOLDING_HISTORY'||data.account_revision!==revision||data.security_id!==stock.security_id||data.ticker!==ticker)throw Error('HOLDING_CHART_CHANGED');
   return {...data,latest_display_fallback:latestDisplayEnabled};
  });
  charts.setSelection({recorded_holding:true,label:latestDisplayEnabled?'已录真实持仓 · 展示行情 · 账户月度目标尚未配置':'已录真实持仓 · 历史 K 线（非今日报价） · 账户月度目标尚未配置',stocks:stocks.map(row=>({...row}))});
  charts.setFills?.(fills);
 }
 async function latest(ticker,stock,interval,signal,revision,boundTarget,current){
  const query=new URLSearchParams({security_id:stock.security_id,interval,bars:'260'});
  const response=await fetchImpl('/api/strategy-display/latest-bars?'+query,{signal,cache:'no-store'});
  if(!response.ok)return null;
  const data=await response.json();
  if(current!==generation||account?.revision!==revision||data.account_revision!==revision||data.target_id!==boundTarget||data.security_id!==stock.security_id||data.ticker!==ticker)throw Error('LATEST_CHART_CHANGED');
  if(data.status!=='DISPLAY_ONLY'||data.executable!==false||!Array.isArray(data.bars)||!data.bars.length||data.bars.length>260||!data.bars.every(bar=>typeof bar.complete==='boolean'))throw Error('LATEST_CHART_INVALID');
  return {...data,status:'AVAILABLE',display_only:true,daily_as_of:data.as_of,latest_quote:{price:Number(data.price),as_of:Number.isFinite(data.price_time)?new Date(data.price_time*1000).toISOString():null,session:data.price_session==='REGULAR'?'REGULAR_LAST':'DAILY_BAR'},last_period_may_be_partial:data.bars.at(-1).complete===false};
 }
 function setTarget(target){
  savedTarget=target?structuredClone(target):null;
  const nextKey=target?JSON.stringify([target.target_id,target.targets,account?.holdings||[]]):null;
  if(nextKey!==null&&nextKey===selectionKey)return;
  clear();if(!target){showHoldings();return;}
  targetId=target.target_id;selectionKey=nextKey;const current=generation;
  const stocks=target.targets.filter(row=>row.quantity>0).map(row=>({...row}));
  for(const holding of account?.holdings||[]){
   if(holding.quantity>0&&!stocks.some(row=>row.security_id===holding.security_id))stocks.push({...holding,recorded_holding:true});
  }
  if(!stocks.length){container.textContent='本月目标为空仓，无入选股票 K 线。';return;}
  charts=createCharts(container,async(ticker,interval,signal)=>{
   const stock=stocks.find(row=>row.ticker===ticker);if(!stock)throw Error('TARGET_STOCK_REQUIRED');
   const revision=account?.revision;
   if(latestDisplayEnabled&&revision){const value=await latest(ticker,stock,interval,signal,revision,target.target_id,current);if(value)return value;}
   if(stock.recorded_holding){
    const query=new URLSearchParams({account_revision:revision,security_id:stock.security_id,interval});
    const response=await fetchImpl('/api/strategy-account/holding-bars?'+query,{signal,cache:'no-store'});
    if(!response.ok)throw Error('HOLDING_CHART_UNAVAILABLE');
    const data=await response.json();
    if(current!==generation||account?.revision!==revision||data.scope!=='RECORDED_HOLDING_HISTORY'||data.account_revision!==revision||data.security_id!==stock.security_id||data.ticker!==ticker)throw Error('HOLDING_CHART_CHANGED');
    return {...data,latest_display_fallback:latestDisplayEnabled};
   }
   const query=new URLSearchParams({target_id:target.target_id,security_id:stock.security_id,interval});
   const response=await fetchImpl('/api/strategy-account/target/bars?'+query,{signal,cache:'no-store'});
   if(!response.ok)throw Error('TARGET_CHART_UNAVAILABLE');
   const data=await response.json();
   if(current!==generation||data.target_id!==target.target_id||data.security_id!==stock.security_id||data.ticker!==ticker)throw Error('TARGET_CHART_CHANGED');
   return {...data,latest_display_fallback:latestDisplayEnabled};
  });
  charts.setSelection({monthly_target:true,label:latestDisplayEnabled?'本月股票 · 展示行情 · 绿涨红跌':`本月目标 · 历史日线截至 ${target.historical_training_cutoff} · 非今日报价 · 绿涨红跌`,stocks:stocks.map(row=>({ticker:row.ticker,security_id:row.security_id,quantity:row.quantity,recorded_holding:row.recorded_holding===true}))});
  charts.setFills?.(fills);
 }
 return {setTarget,refresh(){if(!latestDisplayEnabled)return;if(savedTarget){const value=structuredClone(savedTarget);targetId=null;selectionKey=null;setTarget(value);}else{clear();showHoldings();}},setAccount(value){const changed=account?.revision!==value?.revision;account=value?structuredClone(value):null;fills=Array.isArray(account?.fills)?account.fills.map(fill=>({...fill})):[];if(!targetId&&changed){clear();showHoldings();}else if(changed&&savedTarget){setTarget(savedTarget);charts?.setFills?.(fills);}else charts?.setFills?.(fills);},setFills(value){fills=Array.isArray(value)?value.map(fill=>({...fill})):[];charts?.setFills?.(fills);unconfigured();},destroy(){fills=[];account=null;clear();}};
}
const api={mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StrategyMonthlyTargetCharts=api;
})(typeof globalThis!=='undefined'?globalThis:this);
