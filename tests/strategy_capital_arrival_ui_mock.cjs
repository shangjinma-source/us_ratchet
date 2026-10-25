'use strict';
// All cash fixtures are synthetic; no broker balance or transfer amount is used.
const assert=require('node:assert/strict');
const {createController,browserPendingStore}=require('../web/strategy_capital_controller.js');
(async()=>{
 let pending=null,credited=false,creditCount=0,configured=0,calls=[];
 const store={read:()=>pending,write:v=>{pending=structuredClone(v);},clear:()=>{pending=null;}};
 const dependencies={pendingStore:store,eventId:()=> 'arrival-one',
  readSnapshot:async()=>({account:{revision:'a'.repeat(64),cash_confirmation_valid:true,available_cash:'10234.56'},target:{target_id:'b'.repeat(64)}}),
  request:async(path,body)=>{
   calls.push(path);
   if(path.endsWith('/arrive')){
    assert.equal(body.contribution_amount,'2345.67');
    assert.equal(body.operation,undefined);assert.equal(body.available_balance,undefined);
    if(!credited){credited=true;creditCount++;throw Error('RESPONSE_LOST_AFTER_CREDIT');}
    return {event_id:body.event_id,status:'INTENT_RECORDED',credited:true};
   }
   if(path.endsWith('/status'))return {event_id:body.event_id,status:'CASH_RECORDED',credited:true};
   configured++;return {event_id:body.event_id,status:'CONSUMED_BY_PUBLISHED_TARGET',target_id:'new',credited:true};
  }};
 const first=createController(dependencies);await first.start('2345.67');
 assert(pending);assert.equal(creditCount,1);
 const reloaded=createController(dependencies);
 await reloaded.check();assert.equal(configured,0);assert.equal(creditCount,1);
 await reloaded.resume();assert.equal(creditCount,1);assert.equal(configured,1);assert.equal(pending,null);
 assert.equal(calls.filter(p=>p.endsWith('/arrive')).length,2);
 // An abandoned pre-arrival legacy intent is cleared by read-only reconciliation.
 pending={event_id:'legacy',contribution_amount:'2345.67',expected_revision:'a'.repeat(64),previous_target_id:'b'.repeat(64)};
 const legacy=createController({...dependencies,request:async(path,body)=>{
  assert(path.endsWith('/status'));return {event_id:body.event_id,status:'WITHDRAWN',credited:false};
 }});
 await legacy.check();assert.equal(pending,null);assert.equal(legacy.getState().status,'WITHDRAWN');
 // A credited failure must communicate that cash already moved, never invite another deposit.
 const failed=createController({...dependencies,request:async()=>{
  const error=Error('INCOMPLETE_MARK_DOMAIN');
  error.responseBody={credited:true,recovery_status:'RECOVERY_REQUIRED'};throw error;
 }});
 await failed.start('2345.67');assert.equal(failed.getState().result.credited,true);
 assert.equal(failed.getState().status,'RECOVERY_REQUIRED');assert(pending);
 const values=new Map(),storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 const persisted=browserPendingStore(storage,'one');persisted.write(pending);
 assert.equal(persisted.read().operation,'ARRIVAL_V2');
 console.log('PASS arrival UI: lost credit response, reload read-only, same-event recovery, legacy withdrawal, credited failure');
})().catch(error=>{console.error(error);process.exitCode=1;});
