'use strict';
// Actual page components with a deterministic HTTP double, not browser/backend acceptance.
const assert=require('node:assert/strict');
const dailyMount=require('../web/strategy_daily_mount.js');
const capitalMount=require('../web/strategy_capital_mount.js');
const {httpDependencies}=require('../web/strategy_daily_controller.js');
class Node{
 constructor(tag,doc){Object.assign(this,{tag,ownerDocument:doc,children:[],listeners:{},value:''});}
 appendChild(n){n.parentNode=this;this.children.push(n);}
 replaceChildren(...nodes){this.children=[];nodes.forEach(n=>this.appendChild(n));}
 addEventListener(t,f){(this.listeners[t]??=[]).push(f);}
 removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(x=>x!==f);}
 dispatch(t){for(const f of this.listeners[t]||[])f({target:this,preventDefault(){}});}
 click(){if(!this.disabled)this.type==='submit'?this.parentNode.dispatch('submit'):this.dispatch('click');}
}
const doc=new Node('document',null);doc.createElement=t=>new Node(t,doc);
doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const text=n=>[n.textContent||'',...n.children.map(text)].join(' ');
async function scenario(failPreview){
 let pending=null,credits=0,selections=0,cashSaves=0,previews=0,release;
 let account={revision:'a'.repeat(64),cash_confirmation_valid:true,available_cash:'1000',
  holdings:[{security_id:'S',ticker:'SNDK',quantity:14}]};
 let target={server_month:'2026-11',target_month:'2026-11',target_id:'b'.repeat(64),
  targets:[{security_id:'S',ticker:'SNDK',quantity:14}]};
 const request=async(path,body)=>{
  if(path==='/api/strategy-account')return {account:structuredClone(account)};
  if(path.endsWith('/target'))return structuredClone(target);
  if(path.endsWith('/arrive')){
   credits++;assert.equal(body.previous_target_id,'b'.repeat(64));
   account={...account,available_cash:'1250',revision:'c'.repeat(64)};
   return {status:'INTENT_RECORDED',credited:true,event_id:body.event_id,account_revision:account.revision};
  }
  if(path.endsWith('/configure')){
   selections++;target={...target,target_id:'d'.repeat(64),targets:[
    {security_id:'S',ticker:'SNDK',quantity:10},{security_id:'M',ticker:'MRNA',quantity:5}]};
   return {status:'CONSUMED_BY_PUBLISHED_TARGET',credited:true,event_id:body.event_id,
    target_id:target.target_id,account_revision:account.revision};
  }
  assert.equal(path,'/api/strategy-daily-v3/preview');previews++;
  assert.equal(body.expected_revision,account.revision);assert.equal(body.target_id,'d'.repeat(64));
  await new Promise(resolve=>{release=resolve;});
  if(failPreview)throw Error('SOURCE_UNAVAILABLE');
  const until='2026-11-03T16:00:00Z';
  return {status:'READY',account_revision:account.revision,target_id:target.target_id,
   effective_target_quantities:{S:10,M:5},daily_gate:{rows:[{security_id:'S',action:'SELL'},{security_id:'M',action:'BUY'}]},
   reference_quotes:{S:{sell:'100',reference_valid_until:until},M:{buy:'90',reference_valid_until:until}},
   new_orders:[{security_id:'S',side:'SELL',quantity:4,limit_price:'100',reference_valid_until:until},
    {security_id:'M',side:'BUY',quantity:5,limit_price:'90',reference_valid_until:until}]};
 };
 const daily=dailyMount.mount(new Node('div',doc),{
  ...httpDependencies(request,()=> 'cash-event',{confirmCash:async()=>{cashSaves++;throw Error('UNEXPECTED_CASH_WRITE');}}),
  now:()=>Date.parse('2026-11-03T15:00:00Z'),setTimer:()=>1,clearTimer:()=>{}});
 await daily.ready;
 const capital=capitalMount.mount(new Node('div',doc),{request,eventId:()=> 'same-arrival',
  readSnapshot:async()=>({account:structuredClone(account),target:structuredClone(target)}),
  pendingStore:{read:()=>pending,write:value=>{pending=value;},clear:()=>{pending=null;}},
    onPublished:async()=>{await daily.reloadCash();return daily.refresh();},
  onBalanceChanged:()=>daily.reloadCash(),onBusy:value=>daily.setCapitalBusy(value)});
 capital.elements.amount.value='250';capital.elements.submit.click();capital.elements.submit.click();
 for(let i=0;i<200&&!release;i++)await Promise.resolve();
 assert(release,'publication must reach daily refresh');
 assert(capital.elements.submit.disabled);assert(daily.elements.save.disabled);
 assert.equal(daily.elements.input.value,'1250');assert.equal(previews,1);
 release();await capital.whenIdle();
 assert.equal(credits,1);assert.equal(selections,1);assert.equal(cashSaves,0);assert.equal(pending,null);
 assert(!daily.elements.save.disabled);
 if(failPreview){
  assert.match(capital.elements.status.textContent,/今日建议未更新/);
  assert.doesNotMatch(capital.elements.status.textContent,/今日判断已更新/);
  assert.equal(daily.getState().daily,null);
 }else{
  assert.equal(daily.getState().target.target_id,'d'.repeat(64));
  assert.match(text(daily.elements.summary),/SNDK.*卖出 4.*MRNA.*买入 5/s);
  assert.match(capital.elements.status.textContent,/今日判断已更新/);
 }
 capital.dispose();daily.dispose();
}
(async()=>{await scenario(false);await scenario(true);console.log('PASS capital -> new balance/target -> daily actions; double click and refresh failure');})().catch(e=>{console.error(e);process.exitCode=1;});
