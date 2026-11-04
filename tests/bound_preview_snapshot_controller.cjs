'use strict';
const assert=require('node:assert/strict');
const ui=require('../docs/candidates/strategy_daily_controller_bound_snapshot.js');
const clone=structuredClone;
const now=Date.parse('2026-11-04T09:00:00Z');
async function scenario({verifiedSnapshot=true,mutate=()=>{},during=()=>{}}={}){
 let reads=0,controller;
 const account={revision:'r',holdings:[],available_cash:'100',cash_confirmation_valid:true};
 const target={target_id:'t',proposal_id:'a'.repeat(64),server_month:'2026-11',target_month:'2026-11',targets:[],proposal_targets:[]};
 controller=ui.createController({verifiedSnapshot,now:()=>now,loadAccount:async()=>clone(account),
  loadTarget:async()=>{reads++;return clone(target);},
  saveCash:async()=>{throw Error('NO_WRITES_ALLOWED');},generateTarget:async()=>{throw Error('NO_WRITES_ALLOWED');},
  previewDaily:async()=>{
   const reply={status:'WAIT',account_revision:'r',target_id:'t',proposal_id:'a'.repeat(64),new_orders:[],reference_quotes:{},
    verified_snapshot:{schema:'BOUND_PREVIEW_SNAPSHOT_V1',account:clone(account),target:clone(target),checked_at:'2026-11-04T09:00:00Z'}};
   mutate(reply);during(controller);return reply;
  }});
 let error;
 try{await controller.refresh();}catch(value){error=value;}
 return {reads,error,state:controller.getState()};
}
(async()=>{
 let result=await scenario();assert.equal(result.error,undefined);assert.equal(result.reads,1);assert.equal(result.state.daily.status,'WAIT');
 result=await scenario({verifiedSnapshot:false});assert.equal(result.error,undefined);assert.equal(result.reads,2,'legacy path retains post-preview read');
 for(const mutate of [
  value=>delete value.verified_snapshot,
  value=>value.verified_snapshot.account.revision='other',
  value=>value.verified_snapshot.target.target_id='other',
  value=>value.verified_snapshot.target.proposal_id='other',
  value=>value.verified_snapshot.target.server_month='2026-12',
  value=>value.verified_snapshot.checked_at='invalid',
  value=>value.account_revision='other',
  value=>value.new_orders=[{side:'BUY',security_id:'A',quantity:1}],
 ]){
  result=await scenario({mutate});assert.ok(result.error);assert.equal(result.state.daily,null);assert.equal(result.state.busy,false);
 }
 result=await scenario({during:controller=>controller.invalidate()});
 assert.ok(result.error);assert.equal(result.state.daily,null);
 for(const seconds of [60,-1]){
  result=await scenario({mutate:reply=>{
   const until=new Date(now+seconds*1000).toISOString();
   reply.status='READY';reply.risk_monthly_targets={A:1};
   reply.verified_snapshot.target.proposal_targets=[{security_id:'A',ticker:'TEST',quantity:1}];
   reply.daily_gate={rows:[{security_id:'A',action:'BUY'}]};
   reply.reference_quotes={A:{buy:'10',reference_valid_until:until}};
   reply.new_orders=[{security_id:'A',side:'BUY',quantity:1,limit_price:'10',reference_valid_until:until}];
  }});
  assert.equal(result.error,undefined);
  const displayed=ui.presentation(result.state,now);
  assert.equal(displayed.rows[0].orders.length,seconds>0?1:0,'expired network arrival cannot show an executable order');
 }
 // Cash writes use the same verified transport; retrying a missing snapshot
 // must refresh advice without repeating a committed balance event.
 let balance={revision:'r',available_cash:'100',cash_confirmation_valid:true,holdings:[]};
 const target={target_id:'t',proposal_id:'a'.repeat(64),server_month:'2026-11',target_month:'2026-11',targets:[],proposal_targets:[]};
 let writes=0,missing=false,reads=0;
 const controller=ui.createController({verifiedSnapshot:true,now:()=>now,
  loadAccount:async()=>clone(balance),loadTarget:async()=>{reads++;return clone(target);},
  saveCash:async input=>{assert.equal(input.expected_revision,balance.revision);writes++;balance={...balance,revision:'cash'+writes,available_cash:input.amount};return clone(balance);},
  generateTarget:async()=>{throw Error('UNEXPECTED_RESELECTION');},
  previewDaily:async input=>{
   assert.equal(input.expected_revision,balance.revision);
   const response={status:'WAIT',account_revision:balance.revision,target_id:'t',proposal_id:target.proposal_id,new_orders:[],reference_quotes:{}};
   if(!missing)response.verified_snapshot={schema:'BOUND_PREVIEW_SNAPSHOT_V1',account:clone(balance),target:clone(target),checked_at:new Date(now).toISOString()};
   return response;
  }});
 for(const amount of ['300','50']){
  const before=reads;await controller.saveBalance({amount});
  assert.equal(controller.getState().account.available_cash,amount);
  assert.equal(reads,before+1,'one post-save target read, no post-preview target GET');
 }
 assert.equal(writes,2);
 missing=true;await assert.rejects(controller.saveBalance({amount:'60'}),/DAILY_SNAPSHOT_REQUIRED/);
 assert.equal(controller.getState().cashSaved,true);assert.equal(writes,3);
 missing=false;await controller.refresh();assert.equal(writes,3);assert.equal(controller.getState().account.available_cash,'60');
 console.log('PASS: bound snapshot, legacy fallback, 8 invalid responses, concurrent invalidation, cash increase/decrease and retry; no real account writes');
})().catch(error=>{console.error(error);process.exitCode=1;});
