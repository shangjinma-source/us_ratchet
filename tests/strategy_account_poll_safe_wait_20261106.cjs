'use strict';
const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_account.js');
(async()=>{
 for(const waiting of ['WAIT_REGULAR_SESSION','WAIT_SAVED_TARGET','EMPTY_HOLDINGS']){
  let status='READY';const c=createController({automaticValuationEnabled:false,fetchImpl:async url=>({ok:true,json:async()=>url.endsWith('/valuation')?{status,account_revision:'r1',holdings:[]}:url.endsWith('/restart-performance')?{status:'READY_RECONCILED_NO_EXTERNAL_FLOW',account_revision:'r1',as_of:new Date().toISOString()}:{status:'READY',account:{revision:'r1',cash:'100',cash_confirmation_valid:true,holdings:[],orders:[]}}})});
  await c.load();await c.valuation();assert(c.getState().performance);await c.load();assert(c.getState().performance);
  status=waiting;await c.valuation();assert.equal(c.getState().performance,null);assert.equal(c.getState().valuation,null);
 }
 console.log('PASS every WAIT/EMPTY valuation clears prior certified performance');
})().catch(e=>{console.error(e);process.exitCode=1;});
