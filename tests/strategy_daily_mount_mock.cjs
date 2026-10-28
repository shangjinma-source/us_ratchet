'use strict';
// All cash fixtures are synthetic; no broker balance or transfer amount is used.
const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_daily_mount.js');
const {httpDependencies}=require('../web/strategy_daily_controller.js');
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}
 appendChild(n){n.parentNode=this;this.children.push(n);}
 replaceChildren(...nodes){this.children=[];for(const n of nodes)this.appendChild(n);}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
 removeEventListener(type,fn){this.listeners[type]=(this.listeners[type]||[]).filter(x=>x!==fn);}
 dispatch(type){for(const fn of this.listeners[type]||[])fn({target:this,preventDefault(){}});}
 click(){if(this.disabled)return;if(this.type==='submit')this.parentNode.dispatch('submit');else this.dispatch('click');}
}
const doc=new Node('document',null);doc.createElement=tag=>new Node(tag,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const text=node=>[node.textContent||'',...node.children.flatMap(text)].join(' ');
(async()=>{
 let account={revision:'a',cash_confirmation_valid:true,available_cash:'255864/25',holdings:[{security_id:'S',ticker:'SNDK',quantity:14}]};
 let target={server_month:'2026-10'},cashWrites=0,firstGeneration=true,instance,gate,previewFailure=false;
 let refreshCompleted=0;
 const requests=[],recommended=[],chartChanges=[],errors=[],busyChartCallbacks=[];
 const request=async(path,body)=>{
  requests.push({path,body});
  if(path==='/api/strategy-account')return {account:structuredClone(account)};
  if(path.endsWith('/target'))return structuredClone(target);
  if(path.endsWith('/generate')){
   if(firstGeneration){firstGeneration=false;throw Error('NETWORK');}
   target={server_month:'2026-10',target_month:'2026-10',target_id:'t',targets:[{security_id:'S',ticker:'SNDK',quantity:21}]};
   return structuredClone(target);
  }
  if(previewFailure)throw Error('DAILY_RESPONSE_UNAVAILABLE');
  if(gate)await gate;
  return {status:'READY',account_revision:account.revision,target_id:target.target_id,
   policy_id:'MONTHLY_CAP50_EXIT20',risk_monthly_targets:{S:21},
   effective_target_quantities:{S:10},daily_gate:{rows:[{security_id:'S',action:'SELL'}]},
   reference_quotes:{S:{sell:'10025/100',reference_valid_until:'2026-10-20T16:00:00Z'}},
   new_orders:[{security_id:'S',side:'SELL',quantity:4,limit_price:'10025/100',reference_valid_until:'2026-10-20T16:00:00Z'}]};
 };
 const accountController={getState:()=>({account}),confirmCash:async({amount})=>{
  cashWrites++;instance.accountInvalidated();account={...account,revision:'cash-'+cashWrites,available_cash:amount};return {account};
 }};
 const container=new Node('div',doc),timers=new Map();let tick=Date.parse('2026-10-20T15:00:00Z'),timerId=0;
 instance=mount(container,{newsReviewFetch:async()=>({ok:true,json:async()=>({enabled:false,status:'DISABLED'})}),...httpDependencies(request,()=> 'stable-event',accountController),
  now:()=>tick,setTimer:(fn,delay)=>{timers.set(++timerId,{fn,delay});return timerId;},clearTimer:id=>timers.delete(id),onError:e=>errors.push(e.message),
  onRefreshCompleted:()=>refreshCompleted++,onRecommendedTickers:v=>recommended.push(v),onAccountChanged:()=>{if(instance?.getState().busy)busyChartCallbacks.push("account");},onTargetChanged:(v,options)=>{if(instance?.getState().busy)busyChartCallbacks.push("target");chartChanges.push({v,options});}});
 await instance.ready;
 assert.equal(instance.elements.input.value,'10234.56');
 assert.equal(container.children[0].className,'strategy-monthly-target');
 instance.elements.input.value='50';instance.elements.input.dispatch('input');instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,1);assert.match(text(container),/现金已保存/);
 instance.elements.save.click();await instance.whenIdle();assert.equal(cashWrites,1);
 assert.equal(instance.getState().error,null,'same button resumes interrupted target generation');
 const refreshBefore=refreshCompleted;await instance.refresh();
 assert.equal(refreshCompleted,refreshBefore+1,"same-target refresh must retry latest chart");
 assert.equal(cashWrites,1);assert.match(text(instance.elements.summary),/卖出 4.*\$100.25/);
 assert(!text(container).includes('买卖明细'));assert(!text(container).includes('刷新买卖建议'));assert.match(text(container),/风控将目标从 21 股降至 10 股/);
 const attempts=requests.filter(x=>x.path.endsWith('/generate'));assert.deepEqual(attempts[0].body,attempts[1].body);
 assert(recommended.some(x=>x.includes('SNDK')));assert(chartChanges.some(x=>x.v?.target_id==='t'));
 assert.equal(chartChanges.at(-1).options.container,instance.elements.charts);
 assert.equal(instance.elements.input.value,'50');
 // A recorded fill changes available cash; never offer to save the old balance.
 account={...account,revision:'after-fill',available_cash:'40'};
 await instance.load();assert.equal(instance.elements.input.value,'40');
 assert.equal(cashWrites,1,'loading a new balance must not write cash');
 instance.elements.input.value='37';instance.elements.input.dispatch('input');
 account={...account,revision:'another-fill',available_cash:'35'};
 await instance.load();assert.equal(instance.elements.input.value,'37','preserve an unsaved edit');
 assert.equal(cashWrites,1);
 await instance.reloadCash();assert.equal(instance.elements.input.value,'35');
 await instance.refresh();
 assert.equal([...timers.values()].filter(t=>t.delay!==15000).length,1,'financial expiry remains scheduled separately from news polling');
 const beforeExpiry=requests.length,deadline=[...timers.values()].find(t=>t.delay!==15000);assert.ok(deadline);
 // Resume beyond expiry before the suspended timeout has had a chance to run.
 tick+=deadline.delay;doc.dispatch('visibilitychange');doc.defaultView.dispatch('focus');doc.defaultView.dispatch('pageshow');
 assert.equal(requests.length,beforeExpiry);assert.match(text(instance.elements.summary),/上一条建议/);
 assert.doesNotMatch(text(instance.elements.summary),/卖出 4|\$100\.25/);
 assert.match(text(instance.elements.summary),/上一条建议已失效/);
 assert.equal(instance.getState().daily.new_orders.length,1);
 assert.equal([...timers.values()].filter(t=>t.delay!==15000).length,0);
 tick=Date.parse('2026-10-20T15:00:00Z');
 await instance.refresh();assert.equal([...timers.values()].filter(t=>t.delay!==15000).length,1,'financial expiry remains scheduled separately from news polling');
 let resolve;gate=new Promise(r=>resolve=r);
 const pendingRefresh=instance.refresh();
 while(!instance.getState().busy)await new Promise(r=>setImmediate(r));
 instance.accountInvalidated();resolve();await pendingRefresh.catch(()=>{});
 assert.equal(instance.getState().daily,null);assert.match(text(container),/请求使用了旧版本/);assert.doesNotMatch(text(instance.elements.summary),/\$100\.25/);
 assert.match(text(instance.elements.summary),/待核验/);
 assert.equal(chartChanges.at(-1).v.targets[0].quantity,null,'chart handoff must preserve an unknown cap target');
 assert.equal(instance.getState().target.targets[0].quantity,21,'saved raw target remains unchanged');
 gate=null;await instance.refresh();assert.equal([...timers.values()].filter(t=>t.delay!==15000).length,1,'financial expiry remains scheduled separately from news polling');
 instance.setCapitalBusy(true);assert(instance.elements.save.disabled);assert(instance.elements.input.disabled);
 account={...account,revision:'after-capital',available_cash:'1258023/100'};
 await instance.reloadCash();assert.equal(instance.elements.input.value,'12580.23');assert.equal(cashWrites,1);
 assert(instance.elements.save.disabled);instance.setCapitalBusy(false);assert(!instance.elements.save.disabled);
 // Exercise the actual sole submit button after a successful cash write
 // followed by a failed preview, then retry without another cash event.
 previewFailure=true;
 instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,2);assert.equal(instance.getState().cashSaved,true);
 assert.equal(instance.getState().error,'DAILY_RESPONSE_UNAVAILABLE');
 assert.equal(chartChanges.at(-1).v.targets[0].quantity,null,'failed preview cannot restore uncapped chart quantity');
 assert.equal(instance.elements.save.disabled,false);
 previewFailure=false;
 instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,2);assert.equal(instance.getState().error,null);
 assert.equal(chartChanges.at(-1).v.targets[0].quantity,21,'bound policy target restores the chart quantity');
 assert.match(text(instance.elements.summary),/卖出 4/);
 // Editing the balance after failure must still save the new amount.
 previewFailure=true;instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,3);
 instance.elements.input.value='123';instance.elements.input.dispatch('input');
 previewFailure=false;instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,4);assert.equal(account.available_cash,'123');
 // Two submit events before busy is rendered must share the active work.
 let releaseDuplicate;gate=new Promise(r=>releaseDuplicate=r);
 const writesBeforeDuplicate=cashWrites,errorsBeforeDuplicate=errors.length;
 instance.elements.form.dispatch('submit');
 const firstWork=instance.whenIdle();
 instance.elements.form.dispatch('submit');
 assert.equal(instance.whenIdle(),firstWork,'duplicate submit must retain the original pending work');
 let settled=false;firstWork.then(()=>{settled=true;});
 await new Promise(r=>setImmediate(r));
 assert.equal(settled,false);assert.equal(cashWrites,writesBeforeDuplicate+1);
 releaseDuplicate();await instance.whenIdle();gate=null;
 assert.equal(errors.length,errorsBeforeDuplicate);assert.equal(instance.getState().error,null);
 assert.match(text(instance.elements.summary),/卖出 4/);
 // A fill in another tab may land before this tab receives its notification.
 // Do not silently bind the old input to a freshly read account revision.
 const beforeExternalFill=cashWrites;
 account={...account,revision:'external-fill-before-submit',available_cash:'113'};
 instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,beforeExternalFill,'stale displayed cash must not overwrite a new fill');
 assert.equal(account.available_cash,'113');
 assert.equal(instance.elements.input.value,'113');
 assert.equal(instance.getState().error,'CASH_INPUT_SNAPSHOT_CHANGED');
 assert.match(text(instance.elements.summary),/余额已变化.*未覆盖/);
 instance.elements.save.click();await instance.whenIdle();
 assert.equal(cashWrites,beforeExternalFill+1,'confirmed new snapshot can be saved');
 assert.equal(instance.getState().error,null);
 const generationCount=requests.filter(x=>x.path.endsWith('/generate')).length;
 for(const balance of ['30000','5000']){
  instance.elements.input.value=balance;instance.elements.input.dispatch('input');
  instance.elements.save.click();await instance.whenIdle();
  assert.equal(account.available_cash,balance,'cash total replaces, never adds to previous balance');
  assert.equal(instance.getState().target.target_id,'t','retain the current monthly policy');
 }
 assert.equal(requests.filter(x=>x.path.endsWith('/generate')).length,generationCount);
 assert.match(text(container),/当前可用现金 USD/);
 const beforeRecoveryLock=cashWrites;
 instance.setCapitalBusy(true);instance.elements.form.dispatch('submit');await instance.whenIdle();
 assert.equal(cashWrites,beforeRecoveryLock,'legacy recovery lock also rejects direct form submission');
 instance.setCapitalBusy(false);
 const count=requests.length;instance.dispose();instance.elements.save.click();await instance.whenIdle();
 assert.equal(requests.length,count);assert.equal(timers.size,0);
 assert.equal(doc.listeners.visibilitychange.length,0);assert.equal(doc.defaultView.listeners.focus.length,0);assert.equal(doc.defaultView.listeners.pageshow.length,0);
 assert.deepEqual(busyChartCallbacks,[], 'optional chart callbacks never run during daily transaction');console.log('daily mount submit/click/recovery/invalidation/callbacks PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
