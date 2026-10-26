(function(root){
'use strict';
// V27 recovery primitive. Not mounted until a separately verified release.
const fail=reason=>{throw new Error(reason);};
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const fields=(value,names)=>value&&typeof value==='object'&&!Array.isArray(value)&&
 Object.keys(value).sort().join()===names.sort().join();
function checkedRequest(value){
 if(!fields(value,['reason','expected_revision','previous_target_id'])||
  !['INITIAL','MONTHLY_SELECTION'].includes(value.reason)||!digest(value.expected_revision)||
  !(value.previous_target_id===null||digest(value.previous_target_id)))fail('TARGET_RECOVERY_REQUEST_INVALID');
 return {reason:value.reason,expected_revision:value.expected_revision,previous_target_id:value.previous_target_id};
}
function checkedRecord(value){
 if(!fields(value,['version','event_id','request'])||value.version!==1||
  typeof value.event_id!=='string'||!/^[A-Za-z0-9_.:-]{1,128}$/.test(value.event_id))fail('TARGET_RECOVERY_RECORD_INVALID');
 return {version:1,event_id:value.event_id,request:checkedRequest(value.request)};
}
function create({storage,locks,makeId,key='us-ratchet-pending-monthly-target-v1'}){
 if(!storage||typeof locks?.request!=='function'||typeof makeId!=='function')fail('TARGET_RECOVERY_STORAGE_OR_LOCK_REQUIRED');
 const encode=value=>JSON.stringify(checkedRecord(value));
 function read(){
  const raw=storage.getItem(key);if(raw===null)return null;
  if(typeof raw!=='string'||raw.length>4096)fail('TARGET_RECOVERY_RECORD_INVALID');
  let value;try{value=JSON.parse(raw);}catch(_){fail('TARGET_RECOVERY_RECORD_INVALID');}
  return checkedRecord(value);
 }
 function clear(record){
  const current=read();
  if(!current||encode(current)!==encode(record))fail('TARGET_RECOVERY_STORAGE_CHANGED');
  storage.removeItem(key);
  if(read()!==null)fail('TARGET_RECOVERY_CLEAR_FAILED');
 }
 return {
  // null means recover an existing operation only; it never starts a new one.
  run(request,{submit,verify}){
   const requested=request===null?null:checkedRequest(request);
   return locks.request(key,{mode:'exclusive'},async()=>{
    let record=read();
    if(record&&requested&&JSON.stringify(record.request)!==JSON.stringify(requested))fail('TARGET_WRITE_RECONCILIATION_REQUIRED');
    if(!record){
     if(requested===null)return null;
     record=checkedRecord({version:1,event_id:makeId(),request:requested});
     storage.setItem(key,encode(record));
     const saved=read();if(!saved||encode(saved)!==encode(record))fail('TARGET_RECOVERY_STORAGE_CHANGED');
    }
    let response;
    try{response=await submit({...record.request,event_id:record.event_id});}
    catch(error){
     const body=error.responseBody;
     if(error.responseStatus===409&&body?.status==='BLOCKED'&&
      ['STALE_REVISION','STALE_TARGET','ACCOUNT_CHANGED_DURING_TARGET'].includes(body.reason)&&
      !error.write_may_have_occurred&&!error.reconcile_before_retry&&
      !body.write_may_have_occurred&&!body.reconcile_before_retry){clear(record);error.target_not_committed=true;}
     throw error;
    }
    if(!digest(response?.target_id)||!digest(response?.proposal_id)||
     response.account_revision!==record.request.expected_revision)fail('TARGET_RECOVERY_RESPONSE_INVALID');
    // Caller reads current state here. Read failure preserves recovery. A
    // successful read may report changed bindings; clear the confirmed operation
    // before the caller rejects stale advice, so that recovery cannot deadlock.
    const verification=await verify(response);
    if(!verification||typeof verification.matches!=='boolean')fail('TARGET_RECOVERY_VERIFICATION_REQUIRED');
    clear(record);
    return {response,verification};
   });
  }
 };
}
function dependencies({base,request,recovery}){
 const callbacks={
  submit:body=>request('/api/strategy-account/target/generate',body),
  verify:async response=>{
   const [account,target]=await Promise.all([request('/api/strategy-account'),request('/api/strategy-account/target')]);
   if(!digest(account?.account?.revision)||!digest(target?.target_id)||!digest(target?.proposal_id))fail('TARGET_RECOVERY_STATE_INVALID');
   return {matches:account.account.revision===response.account_revision&&
    target.target_id===response.target_id&&target.proposal_id===response.proposal_id};
  }
 };
 return {...base,
  recoverTarget:async()=>{const value=await recovery.run(null,callbacks);return value?.verification||null;},
  generateTarget:async body=>(await recovery.run(body,callbacks)).response
 };
}
const api={create,dependencies};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
else root.StrategyTargetRecoveryV1=api;
})(typeof globalThis!=='undefined'?globalThis:this);
