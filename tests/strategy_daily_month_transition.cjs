'use strict';
const assert=require('node:assert/strict'),path=require('node:path');
const ui=require(path.resolve(process.env.NEWS_CONTROLLER_CANDIDATE||'web/strategy_daily_controller.js'));
(async()=>{
 let revision='r1',month='2026-10',previews=0,saves=0,generations=0;
 const controller=ui.createController({
  loadAccount:async()=>({revision,available_cash:'100'}),
  loadTarget:async()=>({target_id:month,target_month:month,server_month:'2026-11',targets:[]}),
  saveCash:async()=>{saves++;revision='r2';return {revision};},
  generateTarget:async request=>{assert.equal(request.reason,'MONTHLY_SELECTION');assert.equal(request.expected_revision,'r2');assert.equal(request.previous_target_id,'2026-10');generations++;month='2026-11';return {target_id:month};},
  previewDaily:async binding=>{previews++;assert.equal(binding.target_id,'2026-11');return {status:'WAIT',account_revision:revision,target_id:month,new_orders:[],reference_quotes:{}};}
 });
 await assert.rejects(controller.refresh(),/FRONTIER_TARGET_MONTH/);
 assert.deepEqual([previews,saves,generations],[0,0,0]);
 assert.match(ui.waitingExplanation(controller.getState().error),/本月目标尚未生成/);
 await controller.saveBalance({amount:'100',expected_revision:'r1'});
 assert.deepEqual([previews,saves,generations],[1,1,1]);
 assert.equal(controller.getState().error,null);
 console.log('PASS old-month read does not request preview or write; explicit cash flow still generates new target and previews');
})().catch(error=>{console.error(error);process.exitCode=1;});
