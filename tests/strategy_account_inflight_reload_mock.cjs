'use strict';
const assert=require('node:assert/strict');
const {createController,browserPendingFillStore,render}=require('../web/strategy_account.js');
const fill={ticker:'SNDK',side:'BUY',quantity:2,price:'100',executed_at:'2026-10-16T22:05'};
(async()=>{
 for(const originalCommitsFirst of [false,true]){
  const values=new Map(),requests=[];let release,committed=null,credits=0,ids=0;
  const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const store=browserPendingFillStore(storage,'pending');
  const envelope=()=>({ok:true,json:async()=>({status:'READY',account:{revision:committed?'after':'before',holdings:[],orders:[],cash_confirmation_valid:true,fills:committed?[{fill_id:committed.event.event_id}]:[]}})});
  const commit=body=>{if(committed)assert.deepEqual(body,committed);else{committed=body;credits++;}};
  const fetchImpl=async(_,options)=>{
   if(!options.method)return envelope();
   const body=JSON.parse(options.body);requests.push(body);
   if(requests.length===1)return new Promise(resolve=>release=()=>{commit(body);resolve(envelope());});
   commit(body);return envelope();
  };
  const create=()=>createController({pendingFillStore:store,fetchImpl,makeId:()=>`event-${++ids}`,automaticValuationEnabled:false});
  const first=create();await first.load();const inFlight=first.recordFill(fill);first.dispose();
  const second=create();await second.load();assert(second.getState().pendingFill);assert(store.read());
  assert(!render(second.getState()).includes('data-form="fill"'));
  assert(render(second.getState()).includes('data-action="recover-fill"'));
  assert.throws(()=>second.recordFill(fill),/RECONCILE_REQUIRED/);
  second.dispose();const third=create();await third.load();assert(store.read(),'second reload retains original intent');
  if(originalCommitsFirst){release();await inFlight;}
  await third.recoverFill();
  if(!originalCommitsFirst){release();await inFlight;}
  assert.equal(ids,1);assert.equal(credits,1);assert.equal(requests.length,originalCommitsFirst?1:2);
  assert.equal(store.read(),null);assert(!third.getState().pendingFill);
 }
 console.log('PASS inflight reload race: repeated reload preserves original ID; no new fill form; explicit recovery deduplicates before/after original commit');
})().catch(error=>{console.error(error);process.exitCode=1;});
