(function(root){
'use strict';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function number(v){if(typeof v!=='string'||! /^-?\d+(?:\.\d+)?(?:\/\d+)?$/.test(v))throw Error('绩效金额无效');const p=v.split('/'),n=Number(p[0])/(p.length===2?Number(p[1]):1);if(!Number.isFinite(n))throw Error('绩效金额无效');return n;}
function create(details,container,fetcher,binding){
 let active=true,busy=false,sequence=0,controller=null;
 function clear(){sequence++;if(controller)controller.abort();controller=null;busy=false;container.textContent='展开后读取已录模拟成交的累计表现。';}
 async function load(){
  if(!active||!details.open||busy)return;busy=true;const token=++sequence;controller=new AbortController();container.textContent='正在核验累计纸面表现…';
  try{
   const query=new URLSearchParams({account_id:binding.account_id,expected_revision:binding.revision});
   const response=await fetcher('/api/research_paper/performance?'+query,{cache:'no-store',signal:controller.signal});const data=await response.json();
   if(!active||token!==sequence||!details.open)return;
   if(!response.ok)throw Error('累计表现暂不可用');
   if(data.account_id!==binding.account_id||data.revision!==binding.revision||data.expected_revision!==binding.revision||data.current_plan_id!==binding.plan_id||data.genesis_research_id!==binding.genesis_research_id||data.research_only!==true||data.execution_blocked!==true||data.return_scope!=='PRICE_AND_RECORDED_FILL_FEES_ONLY'||data.total_return_certified!==false||!['COMPLETE','INCOMPLETE'].includes(data.status))throw Error('纸面绩效账户或版本不一致');
   if(data.status==='INCOMPLETE'){container.textContent='观察区间或价格资料尚不完整，暂不展示收益与回撤数字。';return;}
   if(!Number.isSafeInteger(data.recorded_fill_count)||data.recorded_fill_count<0||!Number.isSafeInteger(data.elapsed_calendar_days)||data.elapsed_calendar_days<0)throw Error('绩效计数无效');
   const fees=number(data.recorded_fees);if(fees<0)throw Error('绩效费用无效');
   const validDate=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v+'T00:00:00Z'))&&new Date(v+'T00:00:00Z').toISOString().slice(0,10)===v;
   if(!validDate(data.start_date)||!validDate(data.through_date)||data.start_date>data.through_date)throw Error('绩效日期无效');
   if(data.recorded_fill_count===0||data.elapsed_calendar_days===0){container.textContent='尚未形成交易表现（无已录成交或观察不足一天）；已录费用 $'+fees.toFixed(2)+'。';return;}
   const total=number(data.total_return),dd=number(data.maximum_close_drawdown);
   if(total < -1 || dd < 0 || dd > 1)throw Error('绩效数值范围无效');
   container.innerHTML='<p>已录模拟收益 '+(total*100).toFixed(2)+'% · 收盘回撤 '+(dd*100).toFixed(2)+'% · 已录费用 $'+fees.toFixed(2)+'</p><p class="preview-footnote">'+esc(data.start_date)+' 至 '+esc(data.through_date)+'；按已录成交、费用与收盘价计算；未核全收益，分红等未录事项不推定。收盘回撤不包含盘中波动，不代表实盘收益。</p>';
  }catch(e){if(active&&token===sequence)container.textContent=e.message || '累计表现暂不可用';}
  finally{if(token===sequence)busy=false;}
 }
 details.addEventListener('toggle',()=>{if(details.open)load();else clear();});
 clear();return {destroy(){active=false;clear();},load};
}
if(typeof module!=='undefined'&&module.exports)module.exports={create};root.ResearchPaperPerformance={create};
})(typeof window!=='undefined'?window:globalThis);
