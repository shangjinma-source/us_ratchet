'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');
const {createController,httpDependencies}=require(path.resolve(process.argv[2]||'web/strategy_daily_controller.js'));
(async()=>{
 for(const changed of [false,true]){
 let account={revision:'a'.repeat(64),holdings:[]},target={server_month:'2026-11'};
 let partial=false,cashWrites=0,selections=0,ids=0,previews=0;
 const requests=[];
 const request=async(url,body)=>{
  if(url==='/api/strategy-account')return {account:structuredClone(account)};
  if(url.endsWith('/target')){
   if(partial)throw Error('FRONTIER_PROPOSAL_REQUIRED');
   return structuredClone(target);
  }
  if(url.endsWith('/generate')){
   requests.push(structuredClone(body));
   if(requests.length===1){
    selections++;partial=true;
    target={server_month:'2026-11',target_month:'2026-11',target_id:'c'.repeat(64),targets:[]};
    throw Error('TARGET_UNAVAILABLE');
   }
   assert.deepEqual(body,requests[0]);
   partial=false;target={...target,proposal_id:'d'.repeat(64),proposal_targets:[]};
   return structuredClone(target);
  }
  previews++;assert.equal(body.expected_proposal_id,target.proposal_id);
  return {status:'HOLD',account_revision:account.revision,target_id:target.target_id,
   proposal_id:target.proposal_id,risk_monthly_targets:{},new_orders:[],reference_quotes:{}};
 };
 const accountController={getState:()=>({account}),confirmCash:async()=>{
  cashWrites++;account={...account,revision:'b'.repeat(64)};return {account};
 }};
 const controller=createController(httpDependencies(request,()=>`operation-${++ids}`,accountController));
 await assert.rejects(controller.saveBalance({amount:'50'}),/TARGET_UNAVAILABLE/);
 if(changed){
  account={...account,revision:'e'.repeat(64)};
  await assert.rejects(controller.refresh(),/TARGET_CHANGED_AFTER_GENERATION/);
  assert.equal(previews,0);assert.equal(controller.getState().daily,null);
 }
 await controller.refresh();
 assert.equal(controller.getState().daily.status,'HOLD');
 assert.equal(requests.length,2);assert.equal(ids,1);assert.equal(selections,1);assert.equal(cashWrites,1);
 }
 console.log('PASS incomplete frontier proposal recovery reuses operation and cash');
})().catch(error=>{console.error(error);process.exitCode=1;});
