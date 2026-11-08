(function(root){
'use strict';
// Explicit ROA API; never interprets a legacy V27 target as this strategy.
function createController({request,readAccount,eventId,pendingStore,expectedEpoch,historyStore=null,now=()=>Date.now(),onChange=()=>{}}){
 if(typeof expectedEpoch!=='string'||!expectedEpoch)throw Error('STRATEGY_EPOCH_REQUIRED');
 let pending=pendingStore.read(),generation=0;
 const state={busy:false,account:null,advice:null,lastAdvice:null,lastAdviceAt:null,cashSaved:pending?null:false,error:null};
 try{
  const saved=historyStore?.read();
  if(saved&&Number.isFinite(saved.receivedAt)&&saved.receivedAt<=now()&&saved.advice?.strategy_epoch===expectedEpoch&&saved.advice?.strategy_kind==='ROA_DEFENSIVE_V1'&&Array.isArray(saved.advice.rows)&&saved.advice.rows.length<=32){
   state.lastAdvice=structuredClone(saved.advice);state.lastAdviceAt=saved.receivedAt;
  }
 }catch(_){} // Display history is optional and never authorizes an operation.
 const snapshot=()=>{
  const result=structuredClone({...state,pending});
  if(result.advice?.executable===true&&!(now()>=Date.parse(result.advice.valid_from)&&now()<Math.min(Date.parse(result.advice.valid_until),Date.parse(result.advice.quote_valid_until)))){
   result.advice=null;result.error='ADVICE_QUOTE_EXPIRED';
  }
  return result;
 };
 const emit=()=>onChange(snapshot());
 function keep(value){pendingStore.write(structuredClone(value));pending=structuredClone(value);}
 function clear(){pendingStore.clear();pending=null;}
 async function call(name,body){
  try{return await request('/api/strategy-roa/'+name,body);}
  catch(error){if(error.responseBody)return error.responseBody;throw error;}
 }
 function accept(result,token){
  if(result.cash_saved===true){state.cashSaved=true;clear();}
  else if(result.cash_saved===false){state.cashSaved=false;clear();}
  else if(pending)state.cashSaved=null;
  if(token!==generation)throw Error('ACCOUNT_CHANGED_REFRESH_REQUIRED');
  if(result.advice_ready!==true){
   if(result.account&&result.account.revision===result.account_revision&&result.strategy_kind==='ROA_DEFENSIVE_V1'&&result.strategy_epoch===expectedEpoch)state.account=structuredClone(result.account);
   state.error=result.reason||result.status||'ADVICE_REFRESH_REQUIRED';return;
  }
  const a=result.account,d=result;
  if(!a||!d||a.revision!==result.account_revision||d.account_revision!==a.revision||
     d.strategy_kind!=='ROA_DEFENSIVE_V1'||d.strategy_epoch!==expectedEpoch)throw Error('ADVICE_SNAPSHOT_MISMATCH');
  if(d.executable===true){
   if(d.status!=='READY'||!['OPEN','CLOSE'].includes(d.phase)||!/^[a-f0-9]{64}$/.test(d.target_id)||!/^[a-f0-9]{64}$/.test(d.proposal_id))throw Error('ADVICE_EXECUTION_BINDING_REQUIRED');
   if(!(now()>=Date.parse(d.valid_from)&&now()<Math.min(Date.parse(d.valid_until),Date.parse(d.quote_valid_until))))throw Error('ADVICE_QUOTE_EXPIRED');
  }
  if(typeof d.executable!=='boolean'||!Array.isArray(d.rows))throw Error('ADVICE_SCHEMA_REQUIRED');
  for(const row of d.rows){
   if(typeof row.security_id!=='string'||!row.security_id||!Number.isSafeInteger(row.held)||row.held<0||
      (row.target_quantity!==null&&row.target_quantity!==undefined&&(!Number.isSafeInteger(row.target_quantity)||row.target_quantity<0)))throw Error('ADVICE_ROW_INVALID');
   if(d.executable&&['BUY','SELL'].includes(row.side)){
    const parts=String(row.limit_price).split('/'),price=Number(parts[0])/(parts.length===2?Number(parts[1]):1);
    if(!Number.isSafeInteger(row.quantity)||row.quantity<=0||parts.length>2||!Number.isFinite(price)||price<=0)throw Error('ADVICE_ORDER_INVALID');
   }
  }
  state.account=structuredClone(a);state.advice=structuredClone(d);state.error=null;
  if(d.executable){state.lastAdvice=structuredClone(d);state.lastAdviceAt=now();try{historyStore?.write({advice:state.lastAdvice,receivedAt:state.lastAdviceAt});}catch(_){}}
 }
 async function run(operation){
  if(state.busy)return snapshot();
  state.busy=true;state.advice=null;state.error=null;const token=generation;emit();
  try{await operation(token);}
  catch(error){state.error=error.message;state.advice=null;if(pending)state.cashSaved=null;}
  finally{state.busy=false;emit();}
  return snapshot();
 }
 return {
  getState:snapshot,
  accountInvalidated(){generation++;state.advice=null;emit();},
  save:amount=>run(async token=>{
   if(pending)throw Error('CASH_RECONCILIATION_REQUIRED');
   if(typeof amount!=='string'||!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(amount))throw Error('CASH_AMOUNT_REQUIRED');
   const account=await readAccount();
   if(token!==generation)throw Error('ACCOUNT_CHANGED_REFRESH_REQUIRED');
   if(!account||typeof account.revision!=='string')throw Error('ACCOUNT_REQUIRED');
   keep({expected_revision:account.revision,event:{event_id:eventId(),kind:'CASH_CONFIRM',amount,cash_basis:'AVAILABLE_AFTER_RESERVATIONS'}});
   accept(await call('cash-save-and-preview',pending),token);
  }),
  load:()=>run(async token=>{
   if(pending)throw Error('CASH_RECONCILIATION_REQUIRED');
   accept(await call('snapshot',undefined),token);
  }),
  refresh:()=>run(async token=>{
   if(pending){
    const result=await call('cash-status',pending);
    // Only the server's exact revision-conflict proof can release this intent.
    if(result.cash_saved===false&&result.reason==='CASH_NOT_SAVED_ACCOUNT_CHANGED'){
     clear();state.cashSaved=false;
     throw Error('CASH_NOT_SAVED_ACCOUNT_CHANGED');
    }
    // Not observed can still be an in-flight write. Never resend it here.
    if(result.cash_saved!==true)throw Error(result.reason||'CASH_RECONCILIATION_REQUIRED');
    clear();state.cashSaved=true;
   }
   if(token!==generation)throw Error('ACCOUNT_CHANGED_REFRESH_REQUIRED');
   accept(await call('advice-retry',{}),token);
  })
 };
}
function browserPendingStore(storage,key){
 function validate(value){
  if(!value||Object.keys(value).sort().join()!=='event,expected_revision'||! /^[a-f0-9]{64}$/.test(value.expected_revision))throw Error('CASH_PENDING_RECORD_INVALID');
  const event=value.event;
  if(!event||Object.keys(event).sort().join()!=='amount,cash_basis,event_id,kind'||event.kind!=='CASH_CONFIRM'||event.cash_basis!=='AVAILABLE_AFTER_RESERVATIONS'||
     typeof event.event_id!=='string'||!/^[A-Za-z0-9_.:-]{1,128}$/.test(event.event_id)||typeof event.amount!=='string'||!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(event.amount))throw Error('CASH_PENDING_RECORD_INVALID');
  return value;
 }
 return {read(){const raw=storage.getItem(key);if(raw===null)return null;if(raw.length>2048)throw Error('CASH_PENDING_RECORD_INVALID');return validate(JSON.parse(raw));},
  write(value){const raw=JSON.stringify(validate(value));if(raw.length>2048)throw Error('CASH_PENDING_RECORD_INVALID');storage.setItem(key,raw);},
  clear(){storage.removeItem(key);}};
}
const api={createController,browserPendingStore};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.StrategyRoaController=api;
})(typeof window!=='undefined'?window:globalThis);
