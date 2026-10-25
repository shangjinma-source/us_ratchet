const assert=require('node:assert/strict');
const {createController,render}=require('../web/strategy_account.js');
const fill={ticker:'SNDK',side:'BUY',quantity:2,price:100,executed_at:'2026-10-16T22:05'};
(async()=>{
 let posts=0,ids=0,reads=0,committed=false,failRead=false;
 const controller=createController({makeId:()=>`event-${++ids}`,fetchImpl:async(url,options)=>{
  if(options.method){posts++;committed=true;return {ok:false,json:async()=>({status:'BLOCKED',reason:'DYNAMIC_SOURCE_CHANGED',write_may_have_occurred:true,reconcile_before_retry:true})};}
  reads++;if(failRead)throw Error('unavailable');
  assert.equal(url,'/api/strategy-account');
  return {ok:true,json:async()=>({status:'READY',account:{revision:committed?'r2':'r1',holdings:[],orders:[],cash_confirmation_valid:false,fills:committed?[{fill_id:'event-1'}]:[]}})};
 }});
 await controller.load();
 await assert.rejects(controller.recordFill(fill),e=>e.code==='RECONCILE_REQUIRED'&&e.reconcile_before_retry);
 assert.equal(controller.getState().loaded,false);
 assert(!render(controller.getState()).includes('data-form="fill"'));
 assert.throws(()=>controller.recordFill(fill),/RECONCILE_REQUIRED/);
 assert.equal(posts,1);assert.equal(ids,1);
 failRead=true;await controller.refresh();
 assert.throws(()=>controller.recordFill(fill),/RECONCILE_REQUIRED/);
 failRead=false;await controller.refresh();
 assert.equal(controller.getState().account.revision,'r2');
 assert.match(controller.getState().message,/成交已经记录/);
 assert.equal(posts,1);assert.equal(ids,1);assert.equal(reads,3);
 console.log('PASS post-write reconciliation: no second POST or new ID, failed read remains blocked, committed fill identified');
})().catch(error=>{console.error(error);process.exitCode=1;});
