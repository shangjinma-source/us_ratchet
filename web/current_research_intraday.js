(function(root){
'use strict';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function create(container,fetcher,clock={now:()=>Date.now(),set:(f,n)=>setTimeout(f,n),clear:id=>clearTimeout(id)}){
 let research=null,opened=false,generation=0,controller=null,timer=null,expiry=null,value=null,busy=false;
 const stop=()=>{generation++;if(controller)controller.abort();controller=null;if(timer)clock.clear(timer);if(expiry)clock.clear(expiry);timer=expiry=null;busy=false;value=null;};
 const beijing=v=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
 const price=v=>{if(typeof v!=='string'||!/^\d+(?:\.\d+)?$/.test(v)||!Number.isFinite(Number(v))||Number(v)<=0)throw Error('报价金额无效');return Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});};
 function cents(value){
  if(typeof value!=='string'||value.length>80)throw Error('预算金额无效');
  if(/^\d+\/\d+$/.test(value)){const [n,d]=value.split('/').map(BigInt);if(d===0n||n*100n%d!==0n)throw Error('预算不是整分');return n*100n/d;}
  if(!/^\d+(?:\.\d{1,2})?$/.test(value))throw Error('预算金额无效');
  const [whole,fraction='']=value.split('.');return BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));
 }
 const money=value=>(Number(cents(value))/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
 function render(message=''){
  const persistent=value&&value.stocks.some(s=>s.status==='AVAILABLE'&&s.cap_persistence==='TRANSACTIONAL_LOCAL_SQLITE_MIN_ACROSS_RESTARTS');
  const memory=value&&value.stocks.some(s=>s.status==='AVAILABLE'&&s.cap_persistence==='PROCESS_MEMORY_ONLY_RESET_ON_RESTART');
  const capScope=persistent?'同一研究版本、同一股票当日内的上限已保存，服务重启沿用；现金重配产生新研究版本或换日后重新计算。':memory?'同一服务进程、同一研究版本当日内只下调；服务重启或重新配置可能重置。':'当前尚无已确认保存模式的有效报价。';
  container.innerHTML='<p><strong>盘中保守买价参考</strong></p><p class="preview-caption">取新鲜成交价与已完成 1 分钟低价的较低值。'+capScope+'宁可未成交，不自动追价；报价失效停止建议。已在券商挂出的订单需自行改单，本工具不会同步修改。此挂价规则尚未验证收益改善。股数按输入现金从零建仓计算，不是已有持仓应加买的数量，不自动下单。</p>'+
   (message?'<p class="info-strip">'+esc(message)+'</p>':'')+
   (value&&value.observation_record&&value.observation_record.status==='FAILED'?'<p class="info-strip">本次复盘记录未保存；当前参考不能作为已留存的历史建议。</p>':'')+
   (value?value.stocks.map(s=>s.status==='AVAILABLE'&&Date.parse(s.refresh_by)>clock.now()?'<p><strong>'+esc(s.ticker)+'</strong> · 保守买价参考 $'+price(s.limit_price)+' · 从现金建仓 '+s.fresh_cash_reference.quantity+' 股<br><small>现金 $'+money(s.fresh_cash_reference.cash)+' · 按限价占用 $'+money(s.fresh_cash_reference.notional)+' · 剩余 $'+money(s.fresh_cash_reference.residual_cash)+'（佣金 0，其他费用未计）<br>封存模拟目标 '+s.units+' 股，未修改。最新成交 $'+price(s.last_price)+'（'+esc(beijing(s.last_at))+' 北京时间'+'） · 完成分钟低价 $'+price(s.minute_low)+'（'+esc(beijing(s.minute_end))+' 北京时间'+'） · NY交易日 '+esc(s.session)+'</small></p>':'<p>'+esc(s.ticker)+(s.reason==='FETCH_IN_PROGRESS'?'：行情正在更新，请稍后刷新；暂不显示执行价格或股数。':'：新鲜行情不可用，暂不显示执行价格或股数。')+'</p>').join(''):'')+
   '<button class="btn btn-small" data-intraday-refresh '+(busy?'disabled':'')+'>刷新盘中参考</button>';
  const button=container.querySelector('[data-intraday-refresh]');if(button)button.addEventListener('click',refresh);
 }
 function validate(data){
  if(!data||data.research_id!==research.research_id||data.research_only!==true||data.execution_blocked!==true||!Array.isArray(data.stocks)||!['AVAILABLE','PARTIAL','UNAVAILABLE','ALL_CASH'].includes(data.status))throw Error('盘中报价版本不一致');
  const expected=new Map(research.stocks.map(s=>[s.ticker,s.units]));
  if(!expected.size&&research.selected_security)expected.set(research.selected_security.ticker,0);
  if(data.stocks.length!==expected.size||new Set(data.stocks.map(s=>s.ticker)).size!==expected.size)throw Error('盘中股票范围不一致');
  data.stocks.forEach(s=>{if(expected.get(s.ticker)!==s.units||!['AVAILABLE','UNAVAILABLE'].includes(s.status))throw Error('盘中目标不一致');
   if(s.status==='AVAILABLE'){
    ['last_price','minute_low','observed_cap','limit_price'].forEach(k=>price(s[k]));
    const f=s.fresh_cash_reference;
    if(!f||f.research_id!==research.research_id||!Number.isSafeInteger(f.quantity)||f.quantity<0||f.limit_price!==s.limit_price)throw Error('建仓预算版本无效');
    const cash=cents(f.cash),limit=cents(f.limit_price),notional=cents(f.notional),residual=cents(f.residual_cash);
    if(cash!==cents(research.budget_identity_exact.entered_cash)||cents(f.commission)!==0n||BigInt(f.quantity)!==cash/limit||notional!==BigInt(f.quantity)*limit||notional+residual!==cash)throw Error('建仓资金不守恒');
    const dates=['refresh_by','last_at','minute_start','minute_end','session_open','session_close'].map(k=>Date.parse(s[k]));
    const now=clock.now(),[deadline,last,start,end,opening,closing]=dates;
    if(dates.some(v=>!Number.isFinite(v))||deadline<=now||last>now||end>now||end-start!==60000||start%60000!==0||
       opening>now||now>=closing||last<opening||last>=closing||start<opening||end>closing||
       now-last>120000||now-end>120000||deadline>Math.min(last+120000,end+120000,closing)||
       !/^\d{4}-\d{2}-\d{2}$/.test(s.session)||
       [now,opening,closing].some(t=>new Date(t).toLocaleDateString('sv-SE',{timeZone:'America/New_York'})!==s.session)||
       Number(s.limit_price)>Math.min(Number(s.last_price),Number(s.minute_low)))throw Error('盘中行情过期或价格不一致');
   }
  });return data;
 }
 async function refresh(){
  if(!opened||!research||busy)return;busy=true;value=null;render('正在核验新鲜行情…');const token=generation;controller=new AbortController();
  if(timer)clock.clear(timer);if(expiry)clock.clear(expiry);
  try{const response=await fetcher('/api/research_paper/intraday?research_id='+encodeURIComponent(research.research_id),{signal:controller.signal,cache:'no-store'});const data=await response.json();if(token!==generation||!opened)return;if(!response.ok)throw Error('新鲜行情读取失败');value=validate(data);
   busy=false;render(value.status==='ALL_CASH'?'当前研究目标为全现金，无买价参考。':'');
   const deadlines=value.stocks.filter(s=>s.status==='AVAILABLE').map(s=>Date.parse(s.refresh_by));
   if(deadlines.length)expiry=clock.set(()=>{if(token!==generation)return;value=null;render('行情已过期，价格已撤下，请刷新。');},Math.max(0,Math.min(...deadlines)-clock.now()));
  }catch(e){if(token!==generation)return;busy=false;value=null;render('新鲜行情不可用，暂不显示执行价格。');}
  finally{if(token===generation&&opened){busy=false;timer=clock.set(refresh,30000);}}
 }
 function setResearch(data){stop();research=data;render();if(opened)refresh();}
 function invalidate(){stop();research=null;render('研究版本已变化，请重新读取。');}
 function setOpen(value){opened=value;stop();if(opened&&research)refresh();else render();}
 return {setResearch,invalidate,setOpen,refresh};
}
if(typeof module!=='undefined'&&module.exports)module.exports={create};root.ResearchIntraday={create};
})(typeof window!=='undefined'?window:globalThis);
