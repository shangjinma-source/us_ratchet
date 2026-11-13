const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_roa_mount.js');
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}
 appendChild(node){this.children.push(node);return node;}
 replaceChildren(...nodes){this.children=nodes;}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
 removeEventListener(){}
 dispatchEvent(){}
 async fire(type){for(const fn of this.listeners[type]||[])await fn({preventDefault(){}});}
}
(async()=>{
 const doc=new Node('document');doc.createElement=tag=>new Node(tag,doc);doc.defaultView=new Node('window',doc);
 let time=Date.parse('2026-11-13T16:00:00Z'),calls=[],timers=[];
 const account={revision:'a'.repeat(64),available_cash:'1000',cash_confirmation_valid:true,holdings:[],orders:[]};
 const advice={account,account_revision:account.revision,strategy_kind:'ROA_DEFENSIVE_V1',strategy_epoch:'e',status:'READY',phase:'OPEN',executable:true,advice_ready:true,target_id:'b'.repeat(64),proposal_id:'c'.repeat(64),valid_from:'2026-11-13T14:30:00Z',valid_until:'2026-11-13T21:00:00Z',quote_valid_until:'2026-11-13T16:02:00Z',rows:[]};
 const app=mount(new Node('div',doc),{eventId:()=>String(calls.length),expectedEpoch:'e',now:()=>time,setTimer:fn=>{timers.push(fn);return timers.length;},clearTimer:()=>{},pendingStore:{read:()=>null},request:async(path,body)=>{
  calls.push({path,body});
  if(path.endsWith('broker-cash'))return body?{saved:true}:{account_id:'test',account_revision:account.revision,transfer_revision:'t'};
  if(path.endsWith('funding-preview'))return {status:'FUNDING_PLAN_ONLY',executable:false,account_revision:account.revision,proposal_id:advice.proposal_id,quote_valid_until:advice.quote_valid_until,planned_usmart_buys:[{}],planned_broker_sells:[{symbol:'WDC',broker:'HSBC',quantity:12}],proposed_transfer_credit_usd:'22688/100',hsbc_remaining_if_funded_usd:'77312/100'};
  return advice;
 }});
 await app.ready;
 const {fundingForm,fundingResult,fundingInputs,quota,ownership}=app.elements;
 await fundingForm.fire('submit');assert.match(fundingResult.textContent,/优先使用/);assert.equal(calls.length,1);
 fundingInputs.hsbc.value='1000';quota.checked=true;await fundingForm.fire('submit');
 assert.match(fundingResult.textContent,/226.88/);assert.match(fundingResult.textContent,/未成交卖款/);const table=fundingResult.children.at(-1);assert.deepEqual(table.children.at(-1).children.map(cell=>cell.textContent),['WDC','卖出','汇丰','12']);assert.equal(calls.at(-1).body.hsbc_cash,'1000.00');
 assert.equal(calls.at(-1).body.usmart_cash,'0');assert.ok(!calls.some(c=>c.path.includes('cash-save')));
 await fundingForm.fire('input');assert.match(fundingResult.textContent,/条件已变化/);
 fundingInputs.usmart.value='1001';await fundingForm.fire('submit');assert.match(fundingResult.textContent,/不能超过/);
 fundingInputs.usmart.value='0';await fundingForm.fire('submit');
 account.holdings=[{security_id:'security:a',quantity:12}];
 await app.load();
 const priorCalls=calls.length;await fundingForm.fire('submit');
 assert.match(fundingResult.textContent,/确认现有持仓/);assert.equal(calls.length,priorCalls);
 ownership.checked=true;await fundingForm.fire('submit');
 assert.deepEqual(calls.at(-1).body.broker_holdings,{account_revision:account.revision,positions:[{broker:'HSBC',security_id:'security:a',quantity:12}]});
 account.revision='d'.repeat(64);advice.account_revision=account.revision;await app.load();assert.equal(ownership.checked,false);
 ownership.checked=true;await fundingForm.fire('submit');
 time=Date.parse('2026-11-13T16:02:00Z');timers.at(-1)();assert.match(fundingResult.textContent,/已过期/);
 app.dispose();console.log('PASS funding form: quota, pooled cash, no cash write, changed input, expiry');
})().catch(error=>{console.error(error);process.exitCode=1;});
