'use strict';
const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_capital_controller.js');
(async()=>{
 let stored=null,records=0,revision='a'.repeat(64),statusCalls=0;
 const c=createController({
  request:async(path)=>{if(path.endsWith('/status')){statusCalls++;return {status:'NOT_FOUND',event_id:'event-1'};}
   records++;revision='c'.repeat(64);throw Error('CAPITAL_STALE_SNAPSHOT');},
  readSnapshot:async()=>({account:{revision,cash_confirmation_valid:true},target:{target_id:'b'.repeat(64)}}),
  eventId:()=> 'event-1',
  pendingStore:{read:()=>stored,write:x=>{stored=x;},clear:()=>{stored=null;}}
 });
 await c.start('100');await c.resume();
 assert.equal(records,1);assert.equal(statusCalls,2);
 assert.equal(stored,null);
 assert.equal(c.getState().status,'INTENT_NOT_RECORDED_REFRESH_REQUIRED');
 let otherStored=null;
 const other=createController({
  request:async()=>({status:'CONSUMED_BY_PUBLISHED_TARGET',event_id:'different-event',target_id:'different-target'}),
  readSnapshot:async()=>({account:{revision:'a'.repeat(64),cash_confirmation_valid:true},target:{target_id:'b'.repeat(64)}}),
  eventId:()=> 'expected-event',
  pendingStore:{read:()=>otherStored,write:x=>{otherStored=x;},clear:()=>{otherStored=null;}}
 });
 await other.start('100');
 assert.equal(otherStored.event_id,'expected-event');
 assert.equal(other.getState().error,'CAPITAL_RESPONSE_EVENT_MISMATCH');
 console.log('PASS: proven absent stale intent releases; mismatched event preserves pending');
})().catch(error=>{console.error(error);process.exitCode=1;});
