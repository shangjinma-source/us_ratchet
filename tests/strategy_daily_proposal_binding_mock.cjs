'use strict';
const assert=require('node:assert/strict');
const {createController,presentation,targetRows}=require('../web/strategy_daily_controller.js');
const A='a'.repeat(64),B='b'.repeat(64);
async function run(initial,returned,changed){
 let target={server_month:'2026-10',target_month:'2026-10',target_id:'same-target',targets:[],proposal_targets:[]};
 if(initial!==undefined)target.proposal_id=initial;
 let request;
 const controller=createController({loadAccount:async()=>({revision:'same-account',holdings:[]}),loadTarget:async()=>structuredClone(target),previewDaily:async body=>{
  request=body;
  if(changed!==undefined)target.proposal_id=changed;
  const response={status:'HOLD',account_revision:'same-account',target_id:'same-target',risk_monthly_targets:{},new_orders:[],reference_quotes:{}};
  if(returned!==undefined)response.proposal_id=returned;
  return response;
 }});
 let error;try{await controller.refresh();}catch(e){error=e.message;}
 return {request,error,state:controller.getState()};
}
(async()=>{
 assert.throws(()=>targetRows({proposal_id:A,targets:[]}),/BINDING_MISMATCH/);
 assert.throws(()=>targetRows({proposal_id:A,proposal_targets:[{security_id:'S',ticker:'S',quantity:-1}]}),/BINDING_MISMATCH/);
 assert.deepEqual(targetRows({proposal_id:A,targets:[{security_id:'OLD'}],proposal_targets:[{security_id:'NEW',ticker:'NEW',quantity:2}]}),[{security_id:'NEW',ticker:'NEW',quantity:2}]);
 const legacy=await run();assert.equal(legacy.error,undefined);assert.deepEqual(Object.keys(legacy.request).sort(),['expected_revision','target_id']);
 const good=await run(A,A);assert.equal(good.error,undefined);assert.equal(good.request.expected_proposal_id,A);
 for(const returned of [B,undefined,null,'invalid']){const bad=await run(A,returned);assert.equal(bad.error,'DAILY_RESPONSE_BINDING_MISMATCH');assert.equal(bad.state.daily,null);}
 const changed=await run(A,A,B);assert.equal(changed.error,'SNAPSHOT_CHANGED_DURING_PREVIEW');assert.equal(changed.state.daily,null);
 const upgraded=await run(undefined,undefined,A);assert.equal(upgraded.error,'SNAPSHOT_CHANGED_DURING_PREVIEW');
 const downgrade=await run(undefined,A);assert.equal(downgrade.error,'DAILY_RESPONSE_BINDING_MISMATCH');
 const invalid=await run('invalid','invalid');assert.equal(invalid.request,undefined);
 const model={account:{revision:'r',holdings:[]},target:{target_id:'t',proposal_id:A,targets:[{security_id:'OLD',ticker:'OLD',quantity:99}],proposal_targets:[{security_id:'NEW',ticker:'NEW',quantity:2}]},daily:{status:'HOLD',account_revision:'r',target_id:'t',proposal_id:A,policy_id:'SAVED_FRONTIER_CAP50_EXIT20_V1',risk_monthly_targets:{NEW:2},new_orders:[],reference_quotes:{}},busy:false,error:null};
 const rows=presentation(model).rows;
 assert.equal(rows.find(row=>row.security_id==='NEW').monthly_target,2);
 assert.equal(rows.some(row=>row.security_id==='OLD'),false);
 console.log('proposal binding: legacy, matched, missing, malformed, mismatch and same-target race passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
