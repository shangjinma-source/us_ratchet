'use strict';
const assert=require('node:assert/strict');
const performanceFixture=revision=>{const as_of=new Date().toISOString();return {status:'READY_RECONCILED_NO_EXTERNAL_FLOW',account_revision:revision,as_of,current_equity:'100',valuation_snapshot:{status:'READY',account_revision:revision,valued_at:as_of,strategy_total:'100',market_value:'0',holdings:[]}};};
const {createController}=require('../web/strategy_account.js');
(async()=>{
 for(const waiting of ['WAIT_REGULAR_SESSION','WAIT_SAVED_TARGET','EMPTY_HOLDINGS']){
  let status='READY';const c=createController({automaticValuationEnabled:false,fetchImpl:async url=>({ok:true,json:async()=>url.endsWith('/valuation')?{status,account_revision:'r1',holdings:[]}:url.endsWith('/restart-performance')?performanceFixture('r1'):{status:'READY',account:{revision:'r1',cash:'100',cash_confirmation_valid:true,holdings:[],orders:[]}}})});
  await c.load();await c.valuation();assert(c.getState().performance);await c.load();assert(c.getState().performance);
  status=waiting;await c.valuation();assert.equal(c.getState().performance,null);assert.equal(c.getState().valuation,null);
 }
 console.log('PASS every WAIT/EMPTY valuation clears prior certified performance');
})().catch(e=>{console.error(e);process.exitCode=1;});
