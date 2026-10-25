'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const accountUI=require('../web/strategy_account.js'),dailyUI=require('../web/strategy_daily_controller.js');
(async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const callbackSource=html.slice(html.indexOf('let realStrategyTargetAccountKey ='),html.indexOf('let currentPortfolioResearchVersion ='));
 const panels=new Map();const charts=[];
 const context={window:{RealStrategyMonthlyCharts:{setAccount:a=>charts.push(['account',a?.revision]),setFills:f=>charts.push(['fills',f])}},$:id=>{if(!panels.has(id))panels.set(id,{style:{}});return panels.get(id);},invalidateRealStrategyAdvice:()=>{},realStrategyCashOnlyBlocked:false};
 vm.createContext(context);vm.runInContext(callbackSource,context);
 let account={account_id:'fixture',revision:'a'.repeat(64),cash_confirmation_valid:true,holdings:[],orders:[],fills:[]};
 const target={target_id:'b'.repeat(64),target_month:'2026-10',server_month:'2026-10',targets:[]};
 let writes=0,previews=0,extraLoads=0,generated=0;
 const request=async(path,body)=>{
  if(path.endsWith('/events')){writes++;account={...account,revision:'c'.repeat(64)};return {status:'READY',account:structuredClone(account)};}
  if(path.endsWith('/valuation'))return {status:'READY',account_revision:account.revision,holdings:[]};
  if(path.endsWith('/target'))return structuredClone(target);
  if(path.endsWith('/generate')){generated++;throw Error('must not generate');}
  if(path.endsWith('/preview')){previews++;return {status:'WAIT',detail_status:'WAIT_POLICY_RELEASE',account_revision:account.revision,target_id:target.target_id,new_orders:[],reference_quotes:{}};}
  return {status:'READY',account:structuredClone(account)};
 };
 const accountController=accountUI.createController({fetchImpl:async(path,options)=>({ok:true,json:()=>request(path,options?.body?JSON.parse(options.body):undefined)}),makeId:()=> 'cash-event',onInvalidate:()=>context.invalidateRealStrategyAccountAdvice(),onRender:(_,state)=>context.renderRealStrategyAccountState(state)});
 context.window.RealStrategyAccount=accountController;
 await accountController.load();
 const daily=dailyUI.createController(dailyUI.httpDependencies(request,()=> 'target-event',accountController));
 const originalLoad=daily.load;daily.load=()=>{extraLoads++;return originalLoad();};context.window.RealStrategyDaily=daily;
 await daily.load();extraLoads=0;
 assert.equal(charts.length,0,'startup defers chart updates until initialization completes');
 // Match the actual DOMContentLoaded transition before a user cash submission.
 vm.runInContext('realStrategyInitializing = false;',context);
 await daily.saveBalance({amount:'1,000'});
 assert.equal(writes,1);assert.equal(previews,1);assert.equal(generated,0);assert.equal(extraLoads,0);
 assert.equal(daily.getState().daily.status,'WAIT');assert.equal(daily.getState().cashSaved,true);
 assert(charts.some(x=>x[0]==='account'&&x[1]==='c'.repeat(64)));
 context.invalidateRealStrategyAccountAdvice();assert.equal(daily.getState().daily,null);
 context.renderRealStrategyAccountState({loaded:false,account:null,busy:false});
 assert.equal(panels.get('panelStrategyMonthlyTarget').hidden,false,'transient failure keeps recovery panel');
 assert.equal(panels.get('panelCurrentPortfolioPreview').hidden,true,'no legacy research fallback');
 console.log('PASS actual index callbacks: own CASH_CONFIRM causes no nested load/cancel, one cash write, no reselect; external invalidate retires daily');
})().catch(e=>{console.error(e);process.exitCode=1});
