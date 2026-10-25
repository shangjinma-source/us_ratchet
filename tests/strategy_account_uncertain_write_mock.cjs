'use strict';
const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_account.js');
const fill={ticker:'SNDK',side:'BUY',quantity:2,price:'100',executed_at:'2026-10-16T22:05'};
(async()=>{
 for(const failure of ['network','json','server','null','incomplete']){
  let committed=false,posts=0,ids=0,readFails=false;
  const controller=createController({automaticValuationEnabled:false,makeId:()=>`event-${++ids}`,fetchImpl:async(_,options)=>{
   if(!options.method){
    if(readFails)throw Error('read unavailable');
    return {ok:true,json:async()=>({status:'READY',account:{revision:committed?'after':'before',
     holdings:committed?[{ticker:'SNDK',quantity:2}]:[],orders:[],cash_confirmation_valid:true,
     fills:committed?[{fill_id:'event-1'}]:[]}})};
   }
   posts++;committed=true;
   if(failure==='network')throw Error('connection lost after commit');
   return {ok:failure!=='server',status:failure==='server'?500:200,json:async()=>{
    if(failure==='json')throw Error('truncated response');
    if(failure==='null')return null;
    return failure==='server'?{status:'BLOCKED',reason:'INTERNAL_ERROR'}:{status:'READY'};
   }};
  }});
  await controller.load();
  await assert.rejects(controller.recordFill(fill),e=>e.code==='RECONCILE_REQUIRED');
  assert.equal(controller.getState().loaded,false);
  assert.throws(()=>controller.recordFill(fill),/RECONCILE_REQUIRED/);
  readFails=true;await controller.refresh();
  assert.throws(()=>controller.recordFill(fill),/RECONCILE_REQUIRED/);
  readFails=false;await controller.refresh();
  assert.equal(controller.getState().account.revision,'after');
  assert.match(controller.getState().message,/成交已经记录/);
  assert.equal(posts,1);assert.equal(ids,1);
 }
 console.log('PASS uncertain writes: network, damaged JSON, HTTP 500, null and incomplete responses require reconciliation; failed read blocks; committed fill identified without second POST');
})().catch(error=>{console.error(error);process.exitCode=1;});
