const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_roa_controller.js');
(async()=>{
 let intent=null,writes=0,ids=0,reconciled=false;
 const controller=createController({expectedEpoch:'test',readAccount:async()=>({revision:'a'.repeat(64)}),eventId:()=>`cash-${++ids}`,
 pendingStore:{read:()=>intent,write:value=>{intent=value},clear:()=>{intent=null}},
 request:async(path)=>{
  if(path.endsWith('cash-save-and-preview')){writes++;if(writes===1)throw Error('NETWORK_LOST');return {cash_saved:true,advice_ready:false,reason:'PENDING_OPEN'}}
  if(path.endsWith('cash-status'))return reconciled?{cash_saved:false,reason:'CASH_NOT_SAVED_ACCOUNT_CHANGED'}:{cash_saved:null,reason:'CASH_NOT_YET_OBSERVED'};
  throw Error('Unexpected automatic retry');
 }});
 await controller.save('3000');assert.ok(intent);
 await controller.refresh();assert.ok(intent);assert.equal(writes,1);
 reconciled=true;await controller.refresh();assert.equal(intent,null);assert.equal(writes,1);
 assert.equal(controller.getState().cashSaved,false);assert.equal(controller.getState().error,'CASH_NOT_SAVED_ACCOUNT_CHANGED');
 await controller.save('500');assert.equal(writes,2);assert.equal(controller.getState().cashSaved,true);assert.equal(intent,null);
 console.log('PASS: stale write released only after server proof; no automatic resubmission');
})().catch(error=>{console.error(error);process.exitCode=1});
