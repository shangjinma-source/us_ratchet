'use strict';
const assert=require('node:assert/strict');
const {createController,render}=require('../web/strategy_account.js');
(async()=>{
 for(const invalid of [null,'revision','time','equity','missing']){
  const now=new Date().toISOString();let valueCalls=0,performanceCalls=0;
  const shared={status:'READY',account_revision:'r1',valued_at:now,market_value:'1100',strategy_total:'2100',holdings:[]};
  if(invalid==='revision')shared.account_revision='r2';if(invalid==='time')shared.valued_at='2000-01-01T00:00:00Z';if(invalid==='equity')shared.strategy_total='999';
  const performance={status:'READY_RECONCILED_NO_EXTERNAL_FLOW',account_revision:'r1',as_of:now,current_equity:'2100',initial_equity:'2000',return_fraction:'1/20',valuation_snapshot:invalid==='missing'?null:shared};
  const c=createController({automaticValuationEnabled:false,fetchImpl:async url=>({ok:true,json:async()=>{
   if(url.endsWith('/valuation')){valueCalls++;return {...shared,account_revision:'r1',valued_at:now,market_value:'1200',strategy_total:'2200'};}
   if(url.endsWith('/restart-performance')){performanceCalls++;return performance;}
   return {status:'READY',account:{revision:'r1',cash:'1000',cash_confirmation_valid:true,holdings:[],orders:[]}};
  }})});
  await c.load();await c.valuation();assert.equal(valueCalls,1);assert.equal(performanceCalls,1);
  if(!invalid){assert.equal(c.getState().valuation.strategy_total,c.getState().performance.current_equity);const html=render(c.getState());assert(!html.includes('2,200.00'));assert.equal((html.match(/2,100\.00/g)||[]).length,2);}
  else{assert(!c.getState().performance);assert.equal(c.getState().valuation.strategy_total,'2200');}
 }
 console.log('PASS one shared valuation for both totals; no third quote; mismatched snapshot rejects performance');
})().catch(e=>{console.error(e);process.exitCode=1;});
