'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(process.env.STRATEGY_INDEX_CANDIDATE||'web/index.html','utf8');
const source=html.slice(html.indexOf('async function refreshAll('),html.indexOf('function startStateAutoRefresh()'));
assert(source.includes('reuseInitialPreview'));
async function check({initial=true,enabled=true,revision='r1',daily=null,error=null,expected}){
 let refreshed=0,accountReads=0;
 const nodes=new Map(),state={busy:false,account:{revision},daily,error};
 const context={Date,setTimeout,realStrategyHeaderRefreshing:false,activePage:'daily',reviewPageGeneration:0,
  $:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
  clearError:()=>{},showError:message=>{throw Error(message);},requestBackgroundStrategyValuation:()=>{},
  window:{RealStrategyAccount:{getState:()=>({busy:false,loaded:true,account:{revision:'r1'}}),load:async()=>{accountReads++;}},
   RealStrategyDaily:{ready:Promise.resolve(),initialPreview:enabled,getState:()=>state,refresh:async()=>{refreshed++;}},
   StrategyDailyController:{waitingExplanation:()=>null}}};
 vm.createContext(context);vm.runInContext(source,context);await context.refreshAll(initial);
 assert.equal(accountReads,1);assert.equal(refreshed,expected);
 assert.equal(nodes.get('btnRefresh').disabled,false);
}
(async()=>{
 await check({daily:{status:'WAIT'},expected:0});
 await check({error:'FRONTIER_TARGET_MONTH',expected:0});
 await check({initial:false,daily:{status:'READY'},expected:1});
 await check({revision:'older',daily:{status:'READY'},expected:1});
 await check({error:'DAILY_UI_SNAPSHOT_CHANGED',expected:1});
 await check({enabled:false,daily:{status:'READY'},expected:1});
 await check({expected:1});
 console.log('PASS bootstrap reuse only; manual refresh, account change, invalidation, missing result still reload');
})().catch(error=>{console.error(error);process.exitCode=1;});
