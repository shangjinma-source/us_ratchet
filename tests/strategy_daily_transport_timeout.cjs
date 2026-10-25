'use strict';
const assert=require('node:assert/strict');
const {fetchTransport,createController}=require('../web/strategy_daily_controller.js');
(async()=>{
 for(const bodyStall of [false,true]){
  let signal;
  const request=fetchTransport(async(_,options)=>{
   signal=options.signal;
   if(bodyStall)return {ok:true,json:()=>new Promise(()=>{})};
   return new Promise(()=>{});
  },{timeoutMs:20});
  await assert.rejects(request('/api/strategy-daily-v3/preview',{}),/DAILY_REQUEST_TIMEOUT/);
  assert.equal(signal.aborted,true);
 }
 let late,stall=false,writes=0;
 const account={revision:'r',holdings:[],cash_confirmation_valid:true,available_cash:'100'};
 const target={target_id:'t',target_month:'2026-10',server_month:'2026-10',targets:[]};
 const response=()=>({ok:true,json:async()=>({status:'HOLD',account_revision:'r',target_id:'t',new_orders:[],reference_quotes:{}})});
 const request=fetchTransport(async()=>stall?new Promise(resolve=>late=resolve):response(),{timeoutMs:20});
 const controller=createController({loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),
  saveCash:async()=>{writes++;return structuredClone(account);},previewDaily:body=>request('/api/strategy-daily-v3/preview',body)});
 await controller.refresh();stall=true;
 await assert.rejects(controller.saveBalance({amount:'100'}),/DAILY_REQUEST_TIMEOUT/);
 assert.equal(controller.getState().busy,false);assert.equal(controller.getState().daily,null);
 assert.equal(controller.getState().cashSaved,true);assert.equal(writes,1);
 stall=false;await controller.refresh();assert.equal(controller.getState().daily.status,'HOLD');
 late({ok:true,json:async()=>({status:'READY',account_revision:'OLD',target_id:'OLD'})});
 await new Promise(r=>setImmediate(r));
 assert.equal(controller.getState().daily.status,'HOLD');assert.equal(writes,1);
 const write=fetchTransport(()=>new Promise(()=>{}),{timeoutMs:20});
 await assert.rejects(write('/api/strategy-account/target/generate',{}),e=>e.message==='DAILY_REQUEST_TIMEOUT'&&e.write_may_have_occurred&&e.reconcile_before_retry);
 console.log('PASS timeout: headers, body, queue recovery, no duplicate cash, late response, ambiguous write');
})().catch(e=>{console.error(e);process.exitCode=1;});
