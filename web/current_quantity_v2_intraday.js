(function(root){
'use strict';
const VERSION='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function fraction(v){if(typeof v!=='string'||v.length>160||!/^\d+(?:\.\d+)?(?:\/\d+)?$/.test(v))throw Error('金额无效');const [a,b='1']=v.split('/'),[whole,dec='']=a.split('.');const n=BigInt(whole+dec),d=10n**BigInt(dec.length)*BigInt(b);if(!d)throw Error('金额无效');return [n,d];}
const equal=(a,b)=>a[0]*b[1]===b[0]*a[1],add=(a,b)=>[a[0]*b[1]+b[0]*a[1],a[1]*b[1]],le=(a,b)=>a[0]*b[1]<=b[0]*a[1];
const money=v=>{const [n,d]=fraction(v);const x=Number(n)/Number(d);if(!Number.isFinite(x))throw Error('金额无效');return x.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});};
function create(details,box,fetcher,clock={now:()=>Date.now(),set:(f,n)=>setTimeout(f,n),clear:id=>clearTimeout(id)}){
 let research=null,value=null,seq=0,busy=false,controller=null,timer=null;
 function clear(){seq++;if(controller)controller.abort();if(timer!==null)clock.clear(timer);controller=timer=null;value=null;busy=false;}
 function render(message=''){
  box.innerHTML='<p class="preview-caption">逐股使用研究资金额度与条件目标上限，取新鲜成交价与已完成一分钟低价的较低值。宁可未成交，不自动追价或修改券商订单；本次参考可随新行情改变，尚未验证收益改善。非账户差额单，其他费用未计。</p>'+(message?'<p class="info-strip">'+esc(message)+'</p>':'')+
   (value?value.stocks.map(s=>s.status==='AVAILABLE'&&Date.parse(s.refresh_by)>clock.now()?'<p><strong>'+esc(s.ticker)+'</strong> · 参考限价 $'+money(s.limit_price)+' · 条件数量 '+s.quantity+' 股<br><small>最新成交 $'+money(s.last_price)+' · 完成分钟低价 $'+money(s.minute_low)+' · 到期 '+esc(new Date(s.refresh_by).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))+'（北京时间）</small></p>':'<p>'+esc(s.ticker)+'：'+(s.status==='WAIT_CASH'?'该股额度不足一股':'新鲜行情或身份依据不足')+'，暂无限价与数量参考。</p>').join(''):'')+
   '<button class="btn btn-small" data-v2-refresh '+(busy||!research?'disabled':'')+'>刷新组合盘中参考</button>';
  box.querySelector('[data-v2-refresh]')?.addEventListener('click',refresh);
 }
 function validate(d){
  if(!d||d.research_id!==research.research_id||d.research_version!==VERSION||d.research_only!==true||d.execution_blocked!==true||d.orders_created!==false||!['AVAILABLE','PARTIAL','UNAVAILABLE','ALL_CASH'].includes(d.status)||!Array.isArray(d.stocks))throw Error('版本无效');
  const cash=fraction(research.available_cash_exact),expected=new Map(research.stocks.map(s=>[s.security_id,s]));let sum=[0n,1n],alloc=[0n,1n];
  if(!equal(cash,fraction(d.available_cash))||d.stocks.length!==expected.size||new Set(d.stocks.map(s=>s.security_id)).size!==expected.size)throw Error('资金或范围无效');
  for(const s of d.stocks){const e=expected.get(s.security_id);if(!e||e.ticker!==s.ticker||e.units!==s.target_quantity||!Number.isSafeInteger(s.quantity)||s.quantity<0||s.quantity>e.units||!['AVAILABLE','WAIT_CASH','UNAVAILABLE'].includes(s.status))throw Error('目标无效');
   const amount=fraction(s.notional),budget=fraction(s.allocation_cash);alloc=add(alloc,budget);sum=add(sum,amount);if(!le(amount,budget))throw Error('超出额度');
   if(s.status!=='AVAILABLE'){if(s.limit_price!==null||s.quantity!==0||amount[0]!==0n)throw Error('失效报价未撤下');continue;}
   const limit=fraction(s.limit_price),last=fraction(s.last_price),low=fraction(s.minute_low);
   if(limit[0]<=0n||s.quantity<=0||!le(limit,last)||!le(limit,low)||!equal(amount,[limit[0]*BigInt(s.quantity),limit[1]])||BigInt(s.quantity)!==[BigInt(e.units),budget[0]*limit[1]/(budget[1]*limit[0])].reduce((a,b)=>a<b?a:b))throw Error('数量或限价无效');
   const [deadline,lastAt,start,end,open,close]=['refresh_by','last_at','minute_start','minute_end','session_open','session_close'].map(k=>Date.parse(s[k])),now=clock.now();
   if([deadline,lastAt,start,end,open,close].some(x=>!Number.isFinite(x))||deadline<=now||open>now||now>=close||lastAt>now||lastAt<open||end>now||start<open||end>close||end-start!==60000||start%60000||now-lastAt>120000||now-end>120000||deadline>Math.min(lastAt+120000,end+120000,close)||[now,open,close].some(t=>new Date(t).toLocaleDateString('sv-SE',{timeZone:'America/New_York'})!==s.session))throw Error('报价过期');
  }
  if(!equal(sum,fraction(d.indicative_notional))||!equal(add(sum,fraction(d.remaining_cash)),cash)||!le(alloc,cash))throw Error('总资金不守恒');return d;
 }
 async function refresh(){if(!research||!details.open||busy)return;clear();busy=true;const token=seq;controller=new AbortController();render('正在核验新鲜行情，旧参考已撤下。');try{const r=await fetcher('/api/current_portfolio_research/intraday',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({research_id:research.research_id}),signal:controller.signal,cache:'no-store'});const d=await r.json();if(token!==seq||!details.open)return;if(!r.ok)throw Error('读取失败');value=validate(d);busy=false;render(d.status==='ALL_CASH'?'全现金研究，无股票买价参考。':'');const deadlines=d.stocks.filter(s=>s.status==='AVAILABLE').map(s=>Date.parse(s.refresh_by));if(deadlines.length)timer=clock.set(()=>{if(seq!==token)return;value=null;render('报价已过期，价格和数量已撤下。');},Math.max(0,Math.min(...deadlines)-clock.now()));}catch(e){if(token!==seq)return;busy=false;value=null;render('新鲜行情暂不可用，请稍后手动刷新。');}}
 function invalidate(){clear();research=null;details.hidden=true;details.style.display='none';render('研究现金或版本变化，旧参考已撤下。');}
 function setResearch(d){invalidate();if(!d||d.research_version!==VERSION||d.research_only!==true||d.execution_blocked!==true)return;research=d;details.hidden=false;details.style.display='';render();if(details.open)refresh();}
 details.addEventListener('toggle',()=>{clear();render();if(details.open)refresh();});invalidate();return {setResearch,invalidate,refresh};
}
if(typeof module!=='undefined'&&module.exports)module.exports={create,fraction};
root.QuantityV2Intraday={create};
if(root.document){const details=root.document.getElementById('quantityV2IntradayDetails');if(details)root.QuantityV2Intraday=create(details,root.document.getElementById('quantityV2IntradayBody'),root.fetch.bind(root));}
})(typeof window!=='undefined'?window:globalThis);
