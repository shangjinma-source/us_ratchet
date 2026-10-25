'use strict';
const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_account.js');
const envelope=revision=>({status:'READY',account:{revision,holdings:[],orders:[],fills:[],cash_confirmation_valid:true,available_cash:'100'}});
const response=revision=>({ok:true,json:async()=>envelope(revision)});
(async()=>{
 for(const bodyStall of [false,true]){
  let late,posts=0,signal,revision='old',stall=true;
  const c=createController({requestTimeoutMs:20,automaticValuationEnabled:false,makeId:()=> 'only-id',fetchImpl:async(_,options)=>{
   if(!options.method)return response(revision);
   posts++;signal=options.signal;
   if(!stall)return response(revision);
   if(bodyStall)return {ok:true,json:()=>new Promise(r=>late=r)};
   return new Promise(r=>late=r);
  }});
  await c.load();await assert.rejects(c.confirmCash({amount:'100'}),e=>e.code==='RECONCILE_REQUIRED'&&e.write_may_have_occurred);
  assert.equal(signal.aborted,true);assert.equal(c.getState().busy,false);assert.equal(c.getState().loaded,false);
  assert.throws(()=>c.confirmCash({amount:'100'}),/RECONCILE_REQUIRED/);assert.equal(posts,1);
  revision='server-committed';await c.load();assert.equal(c.getState().account.revision,revision);
  late(bodyStall?envelope('obsolete'):response('obsolete'));await new Promise(r=>setImmediate(r));
  assert.equal(c.getState().account.revision,'server-committed');assert.equal(posts,1);
 }
 let stall=true;
 const c=createController({requestTimeoutMs:20,automaticValuationEnabled:false,fetchImpl:()=>stall?new Promise(()=>{}):Promise.resolve(response('fresh'))});
 await c.load();assert.equal(c.getState().busy,false);assert.match(c.getState().message,/读取超时/);
 stall=false;await c.load();assert.equal(c.getState().account.revision,'fresh');
 console.log('PASS account timeout: headers/body; uncertain write blocks retry; read reconciles; late response ignored; read recovery');
})().catch(e=>{console.error(e);process.exitCode=1;});
