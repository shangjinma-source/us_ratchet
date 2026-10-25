(function(root){
'use strict';
// Arrived capital is credited once by the server; ordinary balance edits stay separate.
function createController({request,readSnapshot,eventId,pendingStore,onChange=()=>{}}){
 let pending=pendingStore.read(),state={busy:false,status:pending?'PENDING_RECOVERY':'IDLE',error:null};
 const snapshot=()=>structuredClone({...state,pending});
 const emit=()=>onChange(snapshot());
 const keep=value=>{pendingStore.write(structuredClone(value));pending=structuredClone(value);};
 async function call(path,body){
  const result=await request('/api/strategy-capital-v2/'+path,body);
  if(result.event_id!==body.event_id)throw Error('CAPITAL_RESPONSE_EVENT_MISMATCH');
  return result;
 }
 function accept(result){
  state.status=result.status;state.result=structuredClone(result);
  if(['CONSUMED_BY_PUBLISHED_TARGET','WITHDRAWN'].includes(result.status)){
   if(result.status==='CONSUMED_BY_PUBLISHED_TARGET'&&!result.target_id)throw Error('CAPITAL_PUBLISHED_TARGET_REQUIRED');
   pendingStore.clear();pending=null;
  }
  return result;
 }
 async function finish(result){
  accept(result);
  if(['ARRIVAL_RECORDED','CASH_RECORDED'].includes(result.status)){
   if(pending?.operation!=='ARRIVAL_V2')throw Error('CAPITAL_ARRIVAL_RECORD_REQUIRED');
   const {operation,...body}=pending;
   result=await call('arrive',body);accept(result);
  }
  if(result.status==='INTENT_RECORDED')result=await call('configure',{event_id:pending.event_id});
  else if(result.status==='PREPARED_PUBLISH_ONLY')result=await call('recover-publication',{event_id:pending.event_id});
  // RECOVERY_REQUIRED is terminal for automatic recovery: never run selection again.
  return accept(result);
 }
 async function run(operation){
  if(state.busy)return snapshot();
  state={...state,busy:true,error:null};emit();
  try{return await operation();}
  catch(error){
   state.status=pending?'PENDING_RECOVERY':'FAILED';state.error=error.message;
   if(error.responseBody){
    state.result={...state.result,...structuredClone(error.responseBody)};
    state.status=error.responseBody.recovery_status||state.status;
   }
   return snapshot();
  }
  finally{state.busy=false;emit();}
 }
 return {
  getState:snapshot,
  // Page reload may reconcile terminal status, but must never credit or select.
  check:()=>run(async()=>pending?accept(await call('status',{event_id:pending.event_id})):snapshot()),
  start:amount=>run(async()=>{
   if(pending)throw Error('CAPITAL_PENDING_OPERATION_REQUIRED');
   if(typeof amount!=='string'||!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(amount)||!Number.isFinite(Number(amount))||Number(amount)<=0)
    throw Error('CAPITAL_AMOUNT_REQUIRED');
   const {account,target}=await readSnapshot();
   if(!account?.cash_confirmation_valid||!account.revision||!target?.target_id)
    throw Error('CAPITAL_CONFIRMED_ACCOUNT_AND_TARGET_REQUIRED');
   // Persist before crediting. Replays use the same event, never a second credit.
   keep({event_id:eventId(),contribution_amount:amount,
    expected_revision:account.revision,previous_target_id:target.target_id,operation:'ARRIVAL_V2'});
   const {operation,...body}=pending;
   return finish(await call('arrive',body));
  }),
  resume:()=>run(async()=>{
   if(!pending)throw Error('CAPITAL_PENDING_OPERATION_REQUIRED');
   const result=await call('status',{event_id:pending.event_id});
   if(result.status==='NOT_FOUND'){
    const {account,target}=await readSnapshot();
    if(account?.revision!==pending.expected_revision||target?.target_id!==pending.previous_target_id){
     // A fresh missing result after the snapshot changed proves this old intent
     // cannot now be recorded by a delayed request (server checks immutable CAS).
     const verified=await call('status',{event_id:pending.event_id});
     if(verified.status!=='NOT_FOUND')return finish(verified);
     pendingStore.clear();pending=null;
     state.status='INTENT_NOT_RECORDED_REFRESH_REQUIRED';
     return snapshot();
    }
    if(pending.operation!=='ARRIVAL_V2')throw Error('CAPITAL_LEGACY_INTENT_NOT_RECORDED');
    const {operation,...body}=pending;
    return finish(await call('arrive',body));
   }
   return finish(result);
  }),
  withdraw:()=>run(async()=>{
   if(!pending)throw Error('CAPITAL_PENDING_OPERATION_REQUIRED');
   return accept(await call('withdraw',{event_id:pending.event_id}));
  })
 };
}
function browserPendingStore(storage,key){
 function validate(value){
  const keys=['event_id','contribution_amount','expected_revision','previous_target_id'];
  if(value?.operation==='ARRIVAL_V2')keys.push('operation');
  if(!value||typeof value!=='object'||Object.keys(value).sort().join()!==keys.sort().join()||
     typeof value.event_id!=='string'||!value.event_id||value.event_id.length>128||
     typeof value.contribution_amount!=='string'||!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(value.contribution_amount)||
     !Number.isFinite(Number(value.contribution_amount))||Number(value.contribution_amount)<=0||!['expected_revision','previous_target_id'].every(k=>/^[a-f0-9]{64}$/.test(value[k])))
   throw Error('CAPITAL_LOCAL_PENDING_INVALID');
  return value;
 }
 return {
  read(){const raw=storage.getItem(key);if(raw===null)return null;
   if(raw.length>2048)throw Error('CAPITAL_LOCAL_PENDING_INVALID');
   return validate(JSON.parse(raw));},
  write(value){const raw=JSON.stringify(validate(value));
   if(raw.length>2048)throw Error('CAPITAL_LOCAL_PENDING_INVALID');
   storage.setItem(key,raw);},
  clear(){storage.removeItem(key);}
 };
}
const api={createController,browserPendingStore};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyCapitalController=api;
})(typeof window!=='undefined'?window:globalThis);
