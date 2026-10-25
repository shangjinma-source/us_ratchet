// Current index hooks + real account and daily controllers, with an isolated API.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {createController:accountController}=require('../web/strategy_account.js');
const {createController:dailyController,httpDependencies,fetchTransport}=require('../web/strategy_daily_controller.js');
const index=fs.readFileSync(require.resolve('../web/index.html'),'utf8');
const hooks=index.slice(index.indexOf('let realStrategyTargetAccountKey = null;'),index.indexOf('let currentPortfolioResearchVersion = null;'));
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const response=value=>({ok:true,status:200,json:async()=>structuredClone(value)});
async function scenario({initial=false,failedGeneration=false,failedPreview=false,latePreview=false}={}){
 let current={account_id:'fixture',revision:'initial',cash:'10000',available_cash:'10000',cash_confirmation_valid:true,
  holdings:[{security_id:'S',ticker:'SNDK',quantity:14}],orders:[],fills:[]};
 let target=initial?{server_month:'2026-10'}:{server_month:'2026-10',target_id:'monthly',target_month:'2026-10',targets:[{security_id:'S',ticker:'SNDK',quantity:14}]};
 let failGeneration=failedGeneration,failPreview=failedPreview,releasePreview=null,delayPreview=false,id=0;
 const calls=[],panels=new Map();
 const context=vm.createContext({window:{},realStrategyCashOnlyBlocked:false,invalidateRealStrategyAdvice:()=>{},
  $:name=>{if(!panels.has(name))panels.set(name,{style:{}});return panels.get(name);}});
 vm.runInContext(hooks,context);
 const fetchImpl=async(url,options={})=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({url,body});
  if(url==='/api/strategy-account')return response({status:'READY',account:current});
  if(url==='/api/strategy-account/events'){
   assert.equal(body.expected_revision,current.revision);
   assert.equal(body.event.kind,'CASH_CONFIRM');
   assert.equal(body.event.cash_basis,'AVAILABLE_AFTER_RESERVATIONS');
   current={...current,revision:'cash-'+body.event.event_id,cash:body.event.amount,available_cash:body.event.amount};
   return response({status:'READY',account:current});
  }
  if(url==='/api/strategy-account/target')return response(target);
  if(url.endsWith('/target/generate')){
   assert.equal(body.reason,'INITIAL');
   assert.equal(body.expected_revision,current.revision);
   if(failGeneration){failGeneration=false;throw Error('GENERATION_RESPONSE_LOST');}
   target={server_month:'2026-10',target_id:'generated',target_month:'2026-10',targets:[{security_id:'S',ticker:'SNDK',quantity:14}]};
   return response(target);
  }
  if(url==='/api/strategy-daily-v3/preview'){
   assert.equal(body.expected_revision,current.revision);
   if(failPreview){failPreview=false;throw Error('PREVIEW_TEMPORARILY_UNAVAILABLE');}
   const result=response({status:'WAIT',reason:'WAIT_POLICY_REVIEW_SESSION',account_revision:current.revision,target_id:target.target_id});
   if(delayPreview){delayPreview=false;return new Promise(resolve=>{releasePreview=()=>resolve(result);});}
   return result;
  }
  throw Error('UNEXPECTED_API '+url);
 };
 const account=accountController({fetchImpl,makeId:()=>`a-${++id}`,automaticValuationEnabled:false,
  onInvalidate:context.invalidateRealStrategyAccountAdvice,
  onRender:(_,state)=>context.renderRealStrategyAccountState(state)});
 context.window.RealStrategyAccount=account;
 const daily=dailyController(httpDependencies(fetchTransport(fetchImpl),()=>`target-${++id}`,account));
 context.window.RealStrategyDaily=daily;
 await account.load();await daily.load();await flush();
 assert.equal(daily.getState().account.revision,'initial');
 const write=()=>daily.saveBalance({amount:'30000',expected_revision:daily.getState().account.revision});
 if(failedGeneration||failedPreview){
  await assert.rejects(write(),/GENERATION_RESPONSE_LOST|PREVIEW_TEMPORARILY_UNAVAILABLE/);
  assert.equal(daily.getState().cashSaved,true);
  assert.equal(current.available_cash,'30000');
  await daily.refresh(); // Same UI retry path: do not write cash again.
 }else await write();
 assert.equal(calls.filter(c=>c.url.endsWith('/events')).length,1);
 assert.equal(current.available_cash,'30000');
 assert.equal(daily.getState().daily.account_revision,current.revision);
 const generations=calls.filter(c=>c.url.endsWith('/generate'));
 assert.equal(generations.length,initial?(failedGeneration?2:1):0);
 if(failedGeneration)assert.deepEqual(generations[0].body,generations[1].body,'retry retains original target event');
 const targetId=target.target_id;
 await daily.saveBalance({amount:'5000',expected_revision:daily.getState().account.revision});
 assert.equal(current.available_cash,'5000');
 assert.equal(current.holdings[0].quantity,14);
 assert.equal(target.target_id,targetId);
 assert.equal(calls.filter(c=>c.url.endsWith('/generate')).length,generations.length);
 if(latePreview){
  delayPreview=true;
  const pending=daily.refresh();
  const observed=pending.then(()=>null,error=>error);
  while(!releasePreview)await flush();
  // A real-account update invalidates the in-flight advice through index hooks.
  current={...current,revision:'external-fill',available_cash:'4900',cash:'4900',holdings:[{security_id:'S',ticker:'SNDK',quantity:15}]};
  await account.load();
  releasePreview();
  assert.match((await observed).message,/SNAPSHOT_CHANGED/);
  await daily.load();await flush();
  assert.equal(daily.getState().account.revision,'external-fill');
  assert.equal(daily.getState().daily,null,'late old advice cannot replace the new account state');
  const writes=calls.filter(c=>c.url.endsWith('/events')).length;
  await assert.rejects(daily.saveBalance({amount:'5000',expected_revision:'initial'}),/CASH_INPUT_SNAPSHOT_CHANGED/);
  assert.equal(calls.filter(c=>c.url.endsWith('/events')).length,writes);
 }
 assert.equal(panels.get('panelStrategyMonthlyTarget').hidden,false);
 account.dispose();daily.invalidate();
}
(async()=>{
 await scenario();
 await scenario({failedPreview:true});
 await scenario({initial:true,failedGeneration:true});
 await scenario({latePreview:true});
 console.log('PASS current page integration: balance increase/decrease, no same-month reselection, recover without duplicate cash, late advice and stale cash rejected');
})().catch(error=>{console.error(error);process.exitCode=1;});
