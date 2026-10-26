'use strict';
// Browser storage/locks are real; intercepted local pages and submit are fixtures.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const context=await browser.newContext();
  const source=fs.readFileSync(path.join(__dirname,'../web/strategy_target_recovery_v1.js'),'utf8');
  await context.route('**/*',route=>route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><script>'+source+'</script>'}));
  const first=await context.newPage(),second=await context.newPage();
  const url='http://127.0.0.1:45555/isolated-target-recovery';
  await first.goto(url);await second.goto(url);
  await first.evaluate(async()=>{
   const controller=StrategyTargetRecoveryV1.create({storage:localStorage,locks:navigator.locks,makeId:()=> 'persisted-operation'});
   try{await controller.run({reason:'MONTHLY_SELECTION',expected_revision:'a'.repeat(64),previous_target_id:'b'.repeat(64)},
    {submit:async()=>{throw Error('LOST_RESPONSE');},verify:async()=>({matches:true})});}
   catch(error){if(error.message!=='LOST_RESPONSE')throw error;}
  });
  await first.reload();
  const firstResult=first.evaluate(async()=>{
   const controller=StrategyTargetRecoveryV1.create({storage:localStorage,locks:navigator.locks,makeId:()=>{throw Error('NEW_ID_FORBIDDEN');}});
   return controller.run(null,{submit:async body=>{
    if(body.event_id!=='persisted-operation')throw Error('WRONG_ID');
    localStorage.setItem('submit-count',String(Number(localStorage.getItem('submit-count')||0)+1));
    window.started=true;await new Promise(resolve=>window.release=resolve);
    return {target_id:'c'.repeat(64),proposal_id:'d'.repeat(64),account_revision:body.expected_revision};
   },verify:async()=>({matches:true})});
  });
  await first.waitForFunction(()=>window.started===true);
  const secondResult=second.evaluate(async()=>{
   window.waiting=true;
   return StrategyTargetRecoveryV1.create({storage:localStorage,locks:navigator.locks,makeId:()=>{throw Error('NEW_ID_FORBIDDEN');}})
    .run(null,{submit:async()=>{throw Error('SECOND_SUBMIT_FORBIDDEN');},verify:async()=>({matches:true})});
  });
  await second.waitForFunction(()=>window.waiting===true);
  await first.evaluate(()=>window.release());
  const results=await Promise.all([firstResult,secondResult]);
  assert.equal(results[0].verification.matches,true);assert.equal(results[1],null);
  assert.equal(await first.evaluate(()=>localStorage.getItem('submit-count')),'1');
  assert.equal(await first.evaluate(()=>localStorage.getItem('us-ratchet-pending-monthly-target-v1')),null);
  console.log('PASS real browser reload + shared storage + two-tab Web Lock recovery (fixture submit; not mounted)');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
