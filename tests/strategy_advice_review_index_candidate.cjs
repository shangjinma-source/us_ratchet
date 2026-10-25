'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict'),vm=require('node:vm');
const path=process.argv[2]||'tmp/advice_review_index_wiring_20261020_v1/index.candidate.html';
const source=fs.readFileSync(path,'utf8');
assert(source.includes('/static/strategy_advice_review.js?v=20261020-v8'));
const excerpt=source.slice(source.indexOf('let legacyReviewRequested = false;'),source.indexOf('function loadLegacyReviewPage()'));
const nodes=new Map(),calls=[];let options,missing=true;
const context={
 Promise,reviewPageGeneration:0,reviewPageLoaded:false,
 $:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
 window:{fetch(){throw Error('unexpected request');},StrategyAdviceReview:{mount:(container,args)=>{
  options=args;calls.push('mount');return {ready:Promise.resolve(),refresh:async()=>calls.push('refresh'),dispose:()=>calls.push('dispose')};
 }}},
 currentReviewNeedsConfiguration:()=>missing,
 loadLegacyReviewPage:async()=>{calls.push('legacy.read');return true;}
};
vm.createContext(context);vm.runInContext(excerpt,context);
(async()=>{
 await context.loadReviewPage();assert.deepEqual(calls,['mount']);
 assert.equal(nodes.get('btnCurrentPlanReview').hidden,true);
 await context.loadReviewPage();assert.deepEqual(calls,['mount','refresh']);
 await options.onLegacy();
 assert.equal(calls.at(-1),'dispose');
 assert.match(nodes.get('goldenPitBody').textContent,/不会用当前余额重新选股/);
 assert.equal(nodes.get('btnCurrentPlanReview').hidden,false);
 await nodes.get('btnCurrentPlanReview').onclick();
 assert.equal(calls.at(-1),'mount');
 missing=false;await options.onLegacy();assert.equal(calls.at(-1),'legacy.read');
 assert.match(nodes.get('goldenPitSubtitle').textContent,/非当前每日策略/);
 context.window.StrategyAdviceReview=null;await nodes.get('btnCurrentPlanReview').onclick();
 assert.match(nodes.get('goldenPitBody').textContent,/尚未启用/);
 assert.equal(nodes.get('btnCurrentPlanReview').hidden,false);
 assert(!excerpt.includes('loadCurrentPortfolioPreview'));
 console.log('candidate new review mount/refresh/dispose/legacy/fallback PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
