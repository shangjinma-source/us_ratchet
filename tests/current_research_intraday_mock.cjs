const assert=require('node:assert/strict'),{create}=require('../web/current_research_intraday.js');
let now=Date.parse('2026-10-14T15:00:00Z'),timers=new Map(),id=0,calls=[],pending=[];
const box={innerHTML:'',querySelector:()=>({addEventListener(){}})};
const clock={now:()=>now,set:(f,n)=>{timers.set(++id,{f,at:now+n});return id;},clear:i=>timers.delete(i)};
const c=create(box,(url,opts)=>{calls.push({url,opts});return new Promise(r=>pending.push(r));},clock);
const research={research_id:'a'.repeat(24),stocks:[{ticker:'SNDK',units:13}],budget_identity_exact:{entered_cash:'20000'}};
const response=()=>({status:'AVAILABLE',research_id:research.research_id,research_only:true,execution_blocked:true,stocks:[{ticker:'SNDK',units:13,fresh_cash_reference:{research_id:research.research_id,cash:'20000.00',quantity:14,limit_price:'1410.25',notional:'19743.50',residual_cash:'256.50',commission:'0.00'},status:'AVAILABLE',last_price:'1412',minute_low:'1410.25',observed_cap:'1410.25',limit_price:'1410.25',last_at:'2026-10-14T14:59:55Z',minute_start:'2026-10-14T14:58:00Z',minute_end:'2026-10-14T14:59:00Z',session_open:'2026-10-14T13:30:00Z',session_close:'2026-10-14T20:00:00Z',refresh_by:'2026-10-14T15:00:10Z',session:'2026-10-14'}]});
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
c.setResearch(research);assert.equal(calls.length,0);c.setOpen(true);c.refresh();assert.equal(calls.length,1);pending.shift()({ok:true,json:async()=>response()});await tick();assert.match(box.innerHTML,/1,410.25/);assert.match(box.innerHTML,/1412|1,412/);assert.match(box.innerHTML,/从现金建仓 14 股/);assert.match(box.innerHTML,/256.50/);
now+=10001;for(const [k,t]of [...timers])if(t.at<=now){timers.delete(k);t.f();}assert.doesNotMatch(box.innerHTML,/1,410.25/);assert.match(box.innerHTML,/已过期/);
c.refresh();c.invalidate();pending.shift()({ok:true,json:async()=>response()});await tick();assert.doesNotMatch(box.innerHTML,/1,410.25/);assert.equal(timers.size,0);
c.setResearch(research);c.setOpen(false);assert.equal(timers.size,0);const count=calls.length;c.refresh();assert.equal(calls.length,count);
c.setOpen(true);while(pending.length)pending.shift()({ok:true,json:async()=>({...response(),research_id:'b'.repeat(24)})});await tick();assert.match(box.innerHTML,/不可用/);assert.doesNotMatch(box.innerHTML,/1,410.25/);c.setOpen(false);assert.equal(timers.size,0);
async function checkSizing(selected,reply,pattern){
 const target={innerHTML:'',querySelector:()=>({addEventListener(){}})};
 const fixed={now:()=>Date.parse('2026-10-14T15:00:00Z'),set:()=>1,clear:()=>{}};
 const local=create(target,async()=>({ok:true,json:async()=>reply}),fixed);
 local.setResearch(selected);local.setOpen(true);await tick();assert.match(target.innerHTML,pattern);local.setOpen(false);
}
// Refresh must remove the still-valid prior price before the pending HTTP resolves.
const freshBox={innerHTML:'',querySelector:()=>({addEventListener(){}})};let finish;
const live=create(freshBox,()=>new Promise(r=>finish=r),{now:()=>Date.parse('2026-10-14T15:00:00Z'),set:()=>1,clear:()=>{}});
live.setResearch(research);live.setOpen(true);finish({ok:true,json:async()=>response()});await tick();assert.match(freshBox.innerHTML,/1,410.25/);
live.refresh();assert.doesNotMatch(freshBox.innerHTML,/1,410.25/);assert.match(freshBox.innerHTML,/正在核验/);
finish({ok:false,json:async()=>({})});await tick();assert.doesNotMatch(freshBox.innerHTML,/1,410.25/);live.setOpen(false);
const wrongQuantity=response();wrongQuantity.stocks[0].fresh_cash_reference.quantity=15;
await checkSizing(research,wrongQuantity,/不可用/);
const wrongCash=response();wrongCash.stocks[0].fresh_cash_reference.cash='22000.00';
await checkSizing(research,wrongCash,/不可用/);
// A future server deadline cannot make stale/misdated source observations fresh.
for(const patch of [
 {last_at:'2026-10-14T14:57:59Z'},
 {minute_start:'2026-10-14T14:56:00Z',minute_end:'2026-10-14T14:57:00Z'},
 {refresh_by:'2026-10-14T15:01:01Z'},
 {minute_start:'2026-10-14T14:57:00Z'},
 {minute_start:'2026-10-14T14:58:01Z',minute_end:'2026-10-14T14:59:01Z'},
 {session_open:'2026-10-14T15:01:00Z'},
 {session:'2026-10-13'},
 {session_close:'2026-10-15T20:00:00Z'},
]){
 const invalid=response();Object.assign(invalid.stocks[0],patch);
 await checkSizing(research,invalid,/不可用/);
}
const unsaved=response();unsaved.observation_record={status:'FAILED'};
await checkSizing(research,unsaved,/本次复盘记录未保存/);
const fetching=response();fetching.status='UNAVAILABLE';fetching.stocks=[{ticker:'SNDK',units:13,status:'UNAVAILABLE',reason:'FETCH_IN_PROGRESS',limit_price:null,refresh_by:null}];
await checkSizing(research,fetching,/行情正在更新/);
const previouslyCash={...research,stocks:[],selected_security:{ticker:'SNDK'},budget_identity_exact:{entered_cash:'1400'}};
const recovered=response();Object.assign(recovered.stocks[0],{units:0,last_price:'1400',minute_low:'1390',observed_cap:'1390.00',limit_price:'1390.00',fresh_cash_reference:{research_id:research.research_id,cash:'1400.00',quantity:1,limit_price:'1390.00',notional:'1390.00',residual_cash:'10.00',commission:'0.00'}});
await checkSizing(previouslyCash,recovered,/从现金建仓 1 股/);
assert.match(box.innerHTML,/宁可未成交，不自动追价；报价失效停止建议/);assert.match(box.innerHTML,/已在券商挂出的订单需自行改单，本工具不会同步修改/);assert.match(box.innerHTML,/当前尚无已确认保存模式的有效报价/);
const memoryMode=response();memoryMode.stocks[0].cap_persistence='PROCESS_MEMORY_ONLY_RESET_ON_RESTART';
await checkSizing(research,memoryMode,/服务重启或重新配置可能重置/);
const durable=response();durable.stocks[0].cap_persistence='TRANSACTIONAL_LOCAL_SQLITE_MIN_ACROSS_RESTARTS';await checkSizing(research,durable,/同一研究版本、同一股票当日内的上限已保存，服务重启沿用/);
console.log('PASS: lazy intraday, expiry, stale version, collapse, exact cash sizing, mismatched budget/quantity rejected, same-winner affordability recovery');
})().catch(e=>{console.error(e);process.exitCode=1;});
