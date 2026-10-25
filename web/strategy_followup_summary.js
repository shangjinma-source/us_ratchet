(function(root){
'use strict';
function value(text){const p=String(text).split('/');return Number(p[0])/(p.length===2?Number(p[1]):1);}
function mount(container){
 const doc=container.ownerDocument;
 const el=(tag,text)=>{const n=doc.createElement(tag);n.textContent=text;return n;};
 const money=x=>'$'+value(x).toFixed(2),percent=x=>(value(x)*100).toFixed(2)+'%';
 let generation=0;
 async function refresh(){
  const token=++generation;container.replaceChildren(el('p','正在核验复盘来源…'));
  try{
   const response=await root.fetch('/api/strategy-followup-v1/summary',{cache:'no-store'});
   if(!response.ok)throw Error('UNAVAILABLE');
   const data=await response.json();if(token!==generation)return;
   if(data.schema!=='DAILY_FOLLOWUP_SUMMARY_V1'||!Array.isArray(data.items)||data.performance_computed!==false)throw Error('SCHEMA');
   container.replaceChildren(el('h3','建议后的价格观察'));
   if(!data.items.length){container.appendChild(el('p','暂无已核验的价格观察。'));return;}
   const table=el('table',''),head=el('tr','');
   ['股票','原建议','观察日期','当时限价范围','观察收盘','相对限价变化','合并记录'].forEach(x=>head.appendChild(el('th',x)));
   table.appendChild(head);
   for(const row of data.items){
    const tr=el('tr','');
    [row.ticker,row.side==='BUY'?'买入':'卖出',row.observation_session,
     money(row.reference_limit_min)+' ～ '+money(row.reference_limit_max),money(row.closing_price),
     percent(row.price_change_min)+' ～ '+percent(row.price_change_max),String(row.advice_observations)+'条']
     .forEach(x=>tr.appendChild(el('td',x)));table.appendChild(tr);
   }
   const scroll=el('div','');scroll.className='monthly-table-scroll';scroll.appendChild(table);container.appendChild(scroll);
   container.appendChild(el('p',data.notice));
  }catch(_){if(token===generation)container.replaceChildren(el('p','复盘来源核验暂不可用，请稍后重新打开复盘页。'));}
 }
 return {refresh,ready:refresh()};
}
root.StrategyFollowupSummary={mount};
})(window);
