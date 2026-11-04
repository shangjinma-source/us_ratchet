'use strict';
const assert=require('node:assert/strict');
const ui=require('../web/strategy_daily_controller.js');
const now=Date.parse('2026-11-04T10:00:00Z');
const clone=structuredClone;
function fixture(){
 const f={calls:[],writes:0,fail:false,hook:()=>{}};
 f.account={revision:'r',available_cash:'100',holdings:[]};
 f.target={target_id:'t',proposal_id:'a'.repeat(64),target_month:'2026-11',server_month:'2026-11',targets:[],proposal_targets:[]};
 f.daily=()=>({status:'WAIT',new_orders:[],reference_quotes:{},account_revision:f.account.revision,
  target_id:f.target.target_id,proposal_id:f.target.proposal_id,
  verified_snapshot:{schema:'BOUND_PREVIEW_SNAPSHOT_V1',checked_at:new Date(now).toISOString(),account:clone(f.account),target:clone(f.target)}});
 f.dependencies={verifiedSnapshot:true,now:()=>now,
  loadAccount:async()=>{f.calls.push('account');return clone(f.account);},
  loadTarget:async()=>{f.calls.push('target');return clone(f.target);},
  loadCurrentAdvice:async expected=>{
   f.calls.push('current');if(f.fail)throw Error('CURRENT_ADVICE_UNAVAILABLE');
   if(expected!==undefined)assert.equal(expected,f.account.revision);
   const value={schema:'CURRENT_ADVICE_READ_V1',orders_created:false,account_mutated:false,
    account:clone(f.account),target:clone(f.target),daily:f.target.target_month===f.target.server_month?f.daily():null};
   f.hook(value);return value;
  },
  previewDaily:async()=>{f.calls.push('preview');return f.daily();},
  saveCash:async input=>{f.calls.push('cash');assert.equal(input.expected_revision,f.account.revision);
   f.writes++;f.account={...f.account,revision:'cash'+f.writes,available_cash:input.amount};return clone(f.account);},
  generateTarget:async input=>{f.calls.push('generate');assert.equal(input.reason,'MONTHLY_SELECTION');
   f.target={...f.target,target_id:'next',target_month:f.target.server_month};return clone(f.target);}
 };
 f.controller=ui.createController(f.dependencies);return f;
}
(async()=>{
 let f=fixture();await f.controller.refresh();assert.deepEqual(f.calls,['current']);
 assert.equal(f.controller.getState().daily.status,'WAIT');
 for(const amount of ['300','50']){
  f.calls.length=0;await f.controller.saveBalance({amount});
  assert.deepEqual(f.calls,['account','cash','current']);
  assert.equal(f.controller.getState().account.available_cash,amount);
 }
 assert.equal(f.writes,2);
 f.fail=true;await assert.rejects(f.controller.saveBalance({amount:'60'}),/CURRENT_ADVICE_UNAVAILABLE/);
 assert.equal(f.controller.getState().cashSaved,true);assert.equal(f.writes,3);
 f.fail=false;f.calls.length=0;await f.controller.refresh();
 assert.deepEqual(f.calls,['current']);assert.equal(f.writes,3);
 for(const mutate of [value=>value.daily.verified_snapshot.account.revision='wrong',value=>value.daily.target_id='wrong',
   value=>value.daily.verified_snapshot.checked_at='bad',value=>value.daily=null,value=>value.orders_created=true]){
  f=fixture();f.hook=mutate;await assert.rejects(f.controller.refresh());assert.equal(f.controller.getState().daily,null);
 }
 f=fixture();f.hook=()=>f.controller.invalidate();await assert.rejects(f.controller.refresh(),/DAILY_UI_SNAPSHOT_CHANGED/);
 assert.equal(f.controller.getState().daily,null);
 f=fixture();f.target.target_month='2026-10';await f.controller.saveBalance({amount:'50'});
 assert.deepEqual(f.calls,['account','cash','current','generate','account','target','preview']);
 assert.equal(f.controller.getState().target.target_month,'2026-11');
 assert.equal(f.writes,1);
 f=fixture();await f.controller.load();assert.deepEqual(f.calls,['account','target'],'plain load stays read-only without advice generation');
 for(const always of [false,true]){
  f=fixture();let attempts=0;const read=f.dependencies.loadCurrentAdvice;
  const controller=ui.createController({...f.dependencies,loadCurrentAdvice:async revision=>{
   attempts++;
   if(always||attempts===1){const error=Error('EVIDENCE_UNAVAILABLE');error.responseStatus=409;
    error.responseBody={status:'WAIT',reason:'EVIDENCE_UNAVAILABLE',new_orders:[],reference_quotes:{},orders_created:false};throw error;}
   return read(revision);
  }});
  if(always)await assert.rejects(controller.saveBalance({amount:'75'}),/EVIDENCE_UNAVAILABLE/);
  else await controller.saveBalance({amount:'75'});
  assert.equal(attempts,2,'retry evidence failure once only');
  assert.equal(f.writes,1,'never retry the cash write');
  assert.equal(controller.getState().cashSaved,true);
 }
 assert.throws(()=>ui.createController({...f.dependencies,verifiedSnapshot:false}),/VERIFIED_SNAPSHOT_REQUIRED/);
 console.log('PASS one current read, cash increase/decrease, saved-write recovery, invalid/stale replies and monthly generation fallback');
})().catch(error=>{console.error(error);process.exitCode=1;});
