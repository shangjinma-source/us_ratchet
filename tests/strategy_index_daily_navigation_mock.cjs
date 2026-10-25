'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/index.html','utf8');
const take=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
const nodes=new Map(),calls=[];
let tick,accountBusy=false,loaded=true,failPreview=false,legacyMissing=true;
const context={requestBackgroundStrategyValuation:()=>{},
 console,Promise,Date,setTimeout,
 $:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
 window:{
  RealStrategyAccount:{getState:()=>({busy:accountBusy,loaded}),refresh:async()=>calls.push('account.refresh'),load:()=>calls.push('account.load')},
  RealStrategyDaily:{ready:Promise.resolve(),getState:()=>({busy:false}),refresh:async()=>{calls.push('daily.refresh');if(failPreview)throw Error('NETWORK');}}
 },
 document:{hidden:false},realStrategyHeaderRefreshing:false,stateRefreshTimer:null,STATE_REFRESH_MS:100,
 setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{},
 currentAdviceReview:null,activePage:'today',legacyReviewRequested:false,reviewPageLoaded:false,reviewPageGeneration:0,
 clearError:()=>calls.push('clearError'),showError:message=>calls.push(message),
 currentReviewNeedsConfiguration:()=>legacyMissing,
 loadLegacyReviewPage:async()=>{calls.push('legacy.get');return true;},
 apiPost:()=>{throw Error('old API forbidden');},
 loadState:()=>{throw Error('old state forbidden');},
 loadCurrentPortfolioPreview:()=>{throw Error('cash-only research forbidden');}
};
vm.createContext(context);
vm.runInContext(take('function showCurrentStrategyReviewWait()', 'function loadLegacyReviewPage()'),context);
vm.runInContext(take('async function refreshAll(', '// Load on startup'),context);
(async()=>{
 await context.refreshAll(true);
 assert.deepEqual(calls,['account.load','daily.refresh','clearError']);
 calls.length=0;
 await context.refreshAll();
 assert.deepEqual(calls,['account.load','daily.refresh','clearError']);
 assert.equal(context.realStrategyHeaderRefreshing,false);
 assert.match(nodes.get('lastUpdated').textContent,/账户与今日建议/);
 context.activePage='review';calls.length=0;
 await context.refreshAll();
 assert.match(nodes.get('goldenPitBody').textContent,/组件尚未启用/);
 assert(!calls.includes('legacy.get'));
 await context.openLegacyStrategyReview();
 assert.match(nodes.get('goldenPitBody').textContent,/不会用当前余额重新选股/);
 assert(!calls.includes('legacy.get'));
 legacyMissing=false;
 await context.openLegacyStrategyReview();
 assert(calls.includes('legacy.get'));
 assert.match(nodes.get('goldenPitSubtitle').textContent,/非当前每日策略/);
 failPreview=true;await context.refreshAll();
 assert(calls.some(value=>value.includes('NETWORK')));
 assert.equal(nodes.get('btnRefresh').disabled,false);
 context.window.StrategyDailyController=require('../web/strategy_daily_controller.js');
 context.window.RealStrategyDaily.refresh=async()=>{calls.push('daily.refresh');throw Error('DOMAIN_POLICY_AUTHORIZATION_TIME');};
 calls.length=0;await context.refreshAll();
 assert(calls.includes('clearError'));assert(!calls.some(value=>value.includes('刷新新策略失败')));
 assert.match(nodes.get('lastUpdated').textContent,/账户与今日建议/);
 context.startStateAutoRefresh();calls.length=0;tick();
 assert.deepEqual(calls,['account.load']);
 context.realStrategyHeaderRefreshing=true;tick();assert.deepEqual(calls,['account.load']);
 console.log('index new refresh/review isolation/background read PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
