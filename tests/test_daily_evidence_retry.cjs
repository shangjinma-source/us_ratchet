const assert=require('node:assert/strict'),path=require('node:path');
const ui=require(process.env.NEWS_CONTROLLER_CANDIDATE?path.resolve(process.env.NEWS_CONTROLLER_CANDIDATE):'../web/strategy_daily_controller.js');
function failure(reason='EVIDENCE_UNAVAILABLE',status=409,body={}){return Object.assign(new Error(reason),{responseStatus:status,responseBody:{status:'WAIT',reason,new_orders:[],orders_created:false,...body}});}
function setup(mode){
 let account={revision:'before',available_cash:'10',cash_confirmation_valid:true,holdings:[]};let target={target_id:'target',server_month:'2026-10',target_month:'2026-10',targets:[]};let previews=0,writes=0,controller,release;const pending=new Promise(resolve=>release=resolve);const seen=[],bindings=[];if(mode.startsWith('v27'))target={...target,proposal_id:'a'.repeat(64),proposal_targets:[{security_id:'S',ticker:'S',quantity:2}]};
 controller=ui.createController({loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),saveCash:async()=>{writes++;account={...account,revision:'saved',available_cash:'20'};return structuredClone(account);},generateTarget:async()=>{throw Error('UNEXPECTED_TARGET_WRITE');},onChange:s=>seen.push(s),previewDaily:async binding=>{
  previews++;bindings.push(structuredClone(binding));
  if(previews===1){
   if(mode==='v27_changed')target={...target,proposal_id:'b'.repeat(64)};
   if(mode==='account')account={...account,revision:'external'};
   if(mode==='target')target={...target,target_id:'external-target'};
   if(mode==='proposal')target={...target,proposal_id:'a'.repeat(64)};
   if(mode==='invalidate')controller.invalidate();
   if(mode==='timeout')throw Error('NETWORK_TIMEOUT');
   if(mode==='other')throw failure('WAIT_KNOWN_ACTION_REVIEW');
   if(mode==='wrong_status')throw failure('EVIDENCE_UNAVAILABLE',500);
   if(mode==='orders')throw failure('EVIDENCE_UNAVAILABLE',409,{new_orders:[{quantity:1}]});
   if(mode==='created')throw failure('EVIDENCE_UNAVAILABLE',409,{orders_created:true});
   if(mode==='quotes')throw failure('EVIDENCE_UNAVAILABLE',409,{reference_quotes:{S:{buy:'5'}}});
   if(mode==='malformed')throw failure('EVIDENCE_UNAVAILABLE',409,{new_orders:undefined});
   if(mode==='not_wait')throw failure('EVIDENCE_UNAVAILABLE',409,{status:'READY'});
   throw failure();
  }
  if(mode==='double')throw failure();
  if(mode==='late_second')await pending;
  return {status:'READY',account_revision:account.revision,target_id:target.target_id,...(target.proposal_id?{proposal_id:target.proposal_id,risk_monthly_targets:{S:2}}:{}),new_orders:[],reference_quotes:{}};
 }});
 return {controller,seen,bindings,release,get previews(){return previews;},get writes(){return writes;}};
}
(async()=>{
 const ok=setup('success');await ok.controller.load();await ok.controller.saveBalance({amount:'20',expected_revision:'before'});assert.equal(ok.writes,1);assert.equal(ok.previews,2);assert.deepEqual(ok.bindings[0],ok.bindings[1]);assert.equal(ok.controller.getState().daily.status,'READY');assert.equal(ok.controller.getState().cashSaved,true);assert.equal(ok.controller.getState().retrying,false);assert.ok(ok.seen.some(s=>s.retrying&&s.busy&&!s.daily));
 const v27=setup('v27_success');await v27.controller.load();await v27.controller.saveBalance({amount:'20'});assert.equal(v27.previews,2);assert.equal(v27.writes,1);assert.equal(v27.bindings[0].expected_proposal_id,'a'.repeat(64));assert.deepEqual(v27.bindings[0],v27.bindings[1]);assert.equal(v27.controller.getState().daily.proposal_id,'a'.repeat(64));
 const changed=setup('v27_changed');await changed.controller.load();await assert.rejects(changed.controller.saveBalance({amount:'20'}),/SNAPSHOT_CHANGED_DURING_PREVIEW/);assert.equal(changed.previews,1);assert.equal(changed.writes,1);
 const late=setup('late_second');await late.controller.load();const operation=late.controller.saveBalance({amount:'20'});const rejection=assert.rejects(operation,/DAILY_UI_SNAPSHOT_CHANGED/);for(let i=0;i<30&&late.previews<2;i++)await new Promise(setImmediate);assert.equal(late.previews,2);late.controller.invalidate();late.release();await rejection;assert.equal(late.writes,1);assert.equal(late.controller.getState().daily,null);
 const twice=setup('double');await twice.controller.load();await assert.rejects(twice.controller.saveBalance({amount:'20'}),/EVIDENCE_UNAVAILABLE/);assert.equal(twice.previews,2);assert.equal(twice.writes,1);assert.equal(twice.controller.getState().cashSaved,true);assert.equal(twice.controller.getState().retrying,false);
 for(const mode of ['account','target','proposal','invalidate','timeout','other','wrong_status','orders','created','quotes','malformed','not_wait']){
  const h=setup(mode);await h.controller.load();await assert.rejects(h.controller.saveBalance({amount:'20'}));assert.equal(h.previews,1,mode);assert.equal(h.writes,1,mode);assert.equal(h.controller.getState().daily,null,mode);assert.equal(h.controller.getState().retrying,false,mode);
 }
 console.log('PASS bounded evidence retry: success, exhausted, exact binding guards, invalidation, timeout/other/status/unsafe payload refusal; one cash write only');
})().catch(e=>{console.error(e);process.exitCode=1;});
