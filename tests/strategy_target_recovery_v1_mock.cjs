'use strict';
const assert=require('node:assert/strict');
const {create}=require('../web/strategy_target_recovery_v1.js');
const request={reason:'MONTHLY_SELECTION',expected_revision:'a'.repeat(64),previous_target_id:'b'.repeat(64)};
const response={target_id:'c'.repeat(64),proposal_id:'d'.repeat(64),account_revision:request.expected_revision};
function fixture(){
 let raw=null,tail=Promise.resolve(),ids=0,posts=0;
 const storage={getItem:()=>raw,setItem:(key,value)=>{raw=value;},removeItem:()=>{raw=null;}};
 const locks={request:(key,options,callback)=>{
  assert.equal(options.mode,'exclusive');const pending=tail.then(callback);tail=pending.catch(()=>{});return pending;
 }};
 const options={storage,locks,makeId:()=>`target-${++ids}`};
 const submit=async()=>{posts++;return {...response};};
 return {options,submit,verify:async()=>({matches:true}),raw:()=>raw,posts:()=>posts,ids:()=>ids};
}
(async()=>{
 let count=0;
 // Response lost after commit; a replacement controller reuses the same ID.
 {
  const f=fixture(),bodies=[];let committed=0;
  const submit=async body=>{
   bodies.push(body);if(bodies.length===1){committed++;throw Error('RESPONSE_LOST');}
   assert.deepEqual(body,bodies[0]);return {...response};
  };
  await assert.rejects(create(f.options).run(request,{submit,verify:f.verify}),/RESPONSE_LOST/);
  const result=await create(f.options).run(null,{submit,verify:f.verify});
  assert(result.verification.matches);assert.equal(f.ids(),1);assert.equal(committed,1);assert.equal(f.raw(),null);count++;
 }
 // Two tabs recovering the same operation cannot concurrently replay it.
 {
  const f=fixture();
  await assert.rejects(create(f.options).run(request,{submit:async()=>{throw Error('PARTIAL');},verify:f.verify}),/PARTIAL/);
  const results=await Promise.all([create(f.options).run(null,f),create(f.options).run(null,f)]);
  assert.equal(results.filter(Boolean).length,1);assert.equal(f.posts(),1);assert.equal(f.ids(),1);count++;
 }
 // Changed current revision is a completed operation, not an endless retry.
 {
  const f=fixture();const result=await create(f.options).run(request,{submit:f.submit,verify:async()=>({matches:false})});
  assert.equal(result.verification.matches,false);assert.equal(f.raw(),null);count++;
 }
 // Failed state read, invalid success response and failed deletion retain ID.
 for(const stage of ['read','response','delete','missing-verification']){
  const f=fixture();
  if(stage==='delete')f.options.storage.removeItem=()=>{throw Error('DELETE_FAILED');};
  await assert.rejects(create(f.options).run(request,{
   submit:stage==='response'?async()=>({...response,account_revision:'e'.repeat(64)}):f.submit,
   verify:stage==='read'?async()=>{throw Error('READ_FAILED');}:
    stage==='missing-verification'?async()=>undefined:f.verify
  }));
  assert(f.raw());assert.equal(f.ids(),1);count++;
 }
 // Malformed storage or write failure never sends an operation.
 for(const stage of ['read','write']){
  const f=fixture();
  if(stage==='read')f.options.storage.getItem=()=>'{invalid';
  else f.options.storage.setItem=()=>{throw Error('WRITE_FAILED');};
  await assert.rejects(create(f.options).run(request,f));assert.equal(f.posts(),0);count++;
 }
 // Only a structured, definite no-commit conflict releases the operation.
 for(const uncertain of [false,true]){
  const f=fixture(),error=Object.assign(Error('STALE_REVISION'),{responseStatus:409,
   responseBody:{status:'BLOCKED',reason:'STALE_REVISION'},write_may_have_occurred:uncertain});
  await assert.rejects(create(f.options).run(request,{submit:async()=>{throw error;},verify:f.verify}));
  assert.equal(f.raw()!==null,uncertain);count++;
 }
 // A new request cannot overwrite a pending operation from another page.
 {
  const f=fixture();await assert.rejects(create(f.options).run(request,{submit:async()=>{throw Error('LOST');},verify:f.verify}));
  const old=f.raw();await assert.rejects(create(f.options).run({...request,expected_revision:'e'.repeat(64)},f),/RECONCILIATION_REQUIRED/);
  assert.equal(f.raw(),old);assert.equal(f.posts(),0);count++;
 }
 assert.throws(()=>create({...fixture().options,locks:null}),/LOCK_REQUIRED/);count++;
 console.log(`${count} persistent target recovery component scenarios PASS (not mounted)`);
})().catch(error=>{console.error(error);process.exitCode=1;});
