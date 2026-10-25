'use strict';
const assert=require('node:assert/strict');
const {createController,browserPendingFillStore}=require('../web/strategy_account.js');
const fill={ticker:'SNDK',side:'BUY',quantity:2,price:'100',executed_at:'2026-10-16T22:05'};
(async()=>{
 for(const committed of [false,true]){
  const values=new Map();let posts=0,readsFail=false,ids=0,healthy=false,accepted=false;
  const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const store=()=>browserPendingFillStore(storage,'pending');
  const fetchImpl=async(_,options)=>{
   if(options.method){posts++;assert(store().read(),'persist before POST');
    if(!healthy)throw Error('lost response');accepted=true;
   }
   if(readsFail)throw Error('read failed');
   return {ok:true,json:async()=>({status:'READY',account:{revision:committed||accepted?'after':'before',
    holdings:[],orders:[],cash_confirmation_valid:true,fills:committed?[{fill_id:'event-1'}]:[]}})};
  };
  const create=()=>createController({pendingFillStore:store(),fetchImpl,makeId:()=>`event-${++ids}`,automaticValuationEnabled:false});
  const first=create();await first.load();
  await assert.rejects(first.recordFill(fill),/RECONCILE_REQUIRED/);first.dispose();
  assert.equal(store().read().eventId,'event-1');
  const reloaded=create();assert.throws(()=>reloaded.recordFill(fill),/RECONCILE_REQUIRED/);
  readsFail=true;await reloaded.load();assert(store().read());
  assert.throws(()=>reloaded.recordFill(fill),/RECONCILE_REQUIRED/);
  readsFail=false;await reloaded.load();assert.equal(!!store().read(),!committed);
  assert.equal(posts,1);assert.equal(ids,1);
  if(committed)assert.match(reloaded.getState().message,/成交已经记录/);
  else{assert.throws(()=>reloaded.recordFill(fill),/RECONCILE_REQUIRED/);healthy=true;await reloaded.recoverFill();assert.equal(ids,1,'same unchanged request reuses original event');assert.equal(posts,2);assert.equal(store().read(),null);}
 }
 const store=browserPendingFillStore({getItem:()=>null,setItem:()=>{throw Error('quota');}},'pending');
 let posts=0;
 const c=createController({pendingFillStore:store,automaticValuationEnabled:false,makeId:()=> 'event',fetchImpl:async(_,o)=>{
  if(o.method)posts++;
  return {ok:true,json:async()=>({status:'READY',account:{revision:'r',holdings:[],orders:[],cash_confirmation_valid:true}})};
 }});
 await c.load();await assert.rejects(c.recordFill(fill),/quota/);assert.equal(posts,0);assert.equal(c.getState().busy,false);
 console.log('PASS reload reconciliation: pending survives controller replacement; failed GET blocks; saved fill identified; uncommitted retry keeps event ID; storage failure sends no POST');
})().catch(error=>{console.error(error);process.exitCode=1;});
