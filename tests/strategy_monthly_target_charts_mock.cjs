const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_monthly_target_charts.js');
(async()=>{
 let loader,selection,destroyed=0,calls=0,resolve,receivedFills;
 const container={replaceChildren(){},textContent:''};
 const c=mount({container,createCharts:(node,load)=>{loader=load;return{destroy(){destroyed++;},setSelection(value){selection=value;},setFills(value){receivedFills=value;}};},fetchImpl:async(url)=>{calls++;assert(url.includes('security_id=A'));return new Promise(r=>resolve=r);}});
 const fill={ticker:'TEST',security_id:'A',side:'BUY',quantity:3,price:10,executed_at:'2026-10-16T15:00:00Z'};
 c.setFills([fill]);assert(container.textContent.includes('尚未配置'));assert(container.textContent.includes('TEST 买入'));
 const target={target_id:'t1',historical_training_cutoff:'2026-10-14',targets:[{security_id:'A',ticker:'TEST',quantity:3}]};
 c.setTarget(target);assert(selection.monthly_target);assert.equal(selection.stocks[0].quantity,3);assert.equal(calls,0);
 assert.deepEqual(receivedFills,[fill]);assert.equal(selection.stocks[0].security_id,'A');
 c.setFills([]);assert.deepEqual(receivedFills,[]);assert.equal(destroyed,0,'fill updates must preserve chart viewport');
 c.setTarget(target);assert.equal(destroyed,0);
 const old=loader('TEST','day');c.setTarget({...target,target_id:'t2'});resolve({ok:true,json:async()=>({status:'AVAILABLE',target_id:'t1',security_id:'A',ticker:'TEST'})});await assert.rejects(old,/TARGET_CHART_CHANGED/);
 const current=loader('TEST','week');resolve({ok:true,json:async()=>({status:'AVAILABLE',target_id:'t2',security_id:'OTHER',ticker:'TEST'})});await assert.rejects(current,/TARGET_CHART_CHANGED/);
 c.setTarget({...target,target_id:'t2',targets:[{...target.targets[0],quantity:1}]});assert.equal(selection.stocks[0].quantity,1,'same signed target must update capped quantity');
 c.setTarget({...target,target_id:'cash',targets:[]});assert(container.textContent.includes('空仓'));c.destroy();
 console.log('PASS target charts: membership, identity binding, stale async, unchanged target, cash target');
})().catch(error=>{console.error(error);process.exitCode=1;});
