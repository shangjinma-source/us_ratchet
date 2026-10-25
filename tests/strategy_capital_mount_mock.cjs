'use strict';
const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_capital_mount.js');
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';this.style={};}
 appendChild(n){n.parentNode=this;this.children.push(n);}
 replaceChildren(...n){this.children=[];n.forEach(x=>this.appendChild(x));}
 addEventListener(t,f){(this.listeners[t]??=[]).push(f);}
 removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(x=>x!==f);}
 dispatch(t){(this.listeners[t]||[]).forEach(f=>f({preventDefault(){}}));}
 click(){if(this.disabled)return;this.type==='submit'?this.parentNode.dispatch('submit'):this.dispatch('click');}
}
const doc={createElement:t=>new Node(t,doc)};
(async()=>{
 let pending=null,requests=[],published=[],fail=true;
 const deps={
  readSnapshot:async()=>({account:{cash_confirmation_valid:true,revision:'a'.repeat(64)},target:{target_id:'b'.repeat(64)}}),
  eventId:()=> 'one-intent',
  pendingStore:{read:()=>pending,write:v=>{pending=v;},clear:()=>{pending=null;}},
  request:async(path,body)=>{
   requests.push({path,body});
   if(path.endsWith('/arrive'))return {status:'INTENT_RECORDED',event_id:body.event_id};
   if(path.endsWith('/configure')&&fail){fail=false;throw Error('NETWORK');}
   if(path.endsWith('/status'))return {status:'PREPARED_PUBLISH_ONLY',event_id:body.event_id};
   return {status:'CONSUMED_BY_PUBLISHED_TARGET',event_id:body.event_id,target_id:'new-target'};
  },onPublished:id=>{published.push(id);}
 };
 const container=new Node('div',doc),ui=mount(container,deps);
 assert.equal(requests.length,0);assert(!ui.elements.form.hidden);
 assert.equal(ui.elements.open,undefined);
 ui.elements.amount.value='250';ui.elements.submit.click();await ui.whenIdle();
 assert(pending);assert(ui.elements.submit.disabled);assert(!ui.elements.recover.hidden);
 ui.dispose();
 const next=mount(container,deps);
 await next.ready;
 assert.equal(requests.length,3); // Loading only checks status, never credits/selects.
 next.elements.recover.click();await next.whenIdle();await Promise.resolve();
 assert.equal(pending,null);assert.deepEqual(published,['new-target']);
 assert.equal(requests.filter(x=>x.path.endsWith('/configure')).length,1);
 assert.equal(requests.filter(x=>x.path.endsWith('/recover-publication')).length,1);
 next.dispose();
 let balanceCalls=0,publishCalls=0,release,errors=0;
 const synchronized=mount(new Node('div',doc),{...deps,
  request:async(path,body)=>path.endsWith('/arrive')?
   {status:'INTENT_RECORDED',event_id:body.event_id,credited:true}:
   {status:'CONSUMED_BY_PUBLISHED_TARGET',event_id:body.event_id,target_id:'sync-target',credited:true,account_revision:'c'.repeat(64)},
  onBalanceChanged:()=>{balanceCalls++;},
  onPublished:()=>{publishCalls++;return new Promise((resolve,reject)=>{release=reject;});},
  onError:()=>{errors++;}
 });
 synchronized.elements.amount.value='250';synchronized.elements.submit.click();
 for(let i=0;i<20&&!release;i++)await Promise.resolve();
 assert.equal(publishCalls,1);assert.equal(balanceCalls,0,'publication must not start a parallel balance reload');
 assert(synchronized.elements.submit.disabled,'keep submission locked while advice reloads');
 assert(synchronized.elements.status.textContent.includes('正在更新今日建议'));
 release(Error('QUOTE_TIMEOUT'));await synchronized.whenIdle();
 assert.equal(errors,1);assert.equal(pending,null,'failed advice refresh must not recreate capital intent');
 assert(synchronized.elements.status.textContent.includes('不要重复录入新增资金'));
 assert(!synchronized.elements.submit.disabled);
 synchronized.dispose();
 for(const mode of ['READY','WAIT','WRONG_TARGET','WRONG_REVISION']){
  const result={account:{revision:'current'},target:{target_id:'new-target'},
   daily:{status:mode==='WAIT'?'WAIT':'READY',target_id:mode==='WRONG_TARGET'?'old-target':'new-target',
    account_revision:mode==='WRONG_REVISION'?'old':'current'}};
  const checked=mount(new Node('div',doc),{...deps,onPublished:async()=>result});
  checked.elements.amount.value='250';checked.elements.submit.click();await checked.whenIdle();
  const message=checked.elements.status.textContent;
  if(mode==='READY')assert.match(message,/今日判断已更新/);
  else if(mode==='WAIT'){assert.match(message,/今日判断暂不可执行/);assert.doesNotMatch(message,/今日判断已更新/);}
  else assert.match(message,/今日建议未更新/);
  const held=checked.elements.status.textContent;
  checked.adviceRefreshed({...result,busy:true});assert.equal(checked.elements.status.textContent,held);
  checked.adviceRefreshed({...result,error:'SOURCE_UNAVAILABLE'});assert.equal(checked.elements.status.textContent,held);
  checked.adviceRefreshed({account:{revision:'current'},target:{target_id:'new-target'},
   daily:{status:'WAIT',target_id:'new-target',account_revision:'current'}});
  assert.match(checked.elements.status.textContent,/今日判断暂不可执行/);
  assert.equal(pending,null,'advice failure must never recreate a credited intent');
  checked.dispose();
 }
 pending=null;
 const idleContainer=new Node('div',doc),beforeRequests=requests.length;
 const idleRecovery=mount(idleContainer,{...deps,recoveryOnly:true});
 assert.equal(idleContainer.hidden,true,'normal page has no second cash entry');
 assert.equal(idleRecovery.elements.form.hidden,true);
 idleRecovery.elements.amount.value='5000';idleRecovery.elements.form.dispatch('submit');
 await idleRecovery.whenIdle();
 assert.equal(requests.length,beforeRequests,'hidden legacy form cannot start a new credit');
 idleRecovery.dispose();
 pending={event_id:'legacy-pending',contribution_amount:'250',expected_revision:'a'.repeat(64),
  previous_target_id:'b'.repeat(64),operation:'ARRIVAL_V2'};
 let cashLocked=false;
 const recoveryContainer=new Node('div',doc);
 const legacy=mount(recoveryContainer,{...deps,recoveryOnly:true,onBusy:v=>{cashLocked=v;}});
 await legacy.ready;
 assert.equal(recoveryContainer.hidden,false);
 assert.equal(legacy.elements.form.hidden,true);
 assert.equal(legacy.elements.recover.hidden,false);
 assert.equal(cashLocked,true,'ordinary cash writes wait until legacy operation resolves');
 legacy.elements.recover.click();await legacy.whenIdle();
 assert.equal(pending,null);
 assert.equal(cashLocked,false);
 assert.equal(legacy.elements.form.hidden,true,'resolving legacy state never reopens deposit form');
 legacy.dispose();
 console.log('PASS explicit capital UI and recovery-only single cash entry');
})().catch(e=>{console.error(e);process.exitCode=1;});
