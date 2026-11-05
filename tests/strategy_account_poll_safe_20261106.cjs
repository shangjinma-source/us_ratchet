'use strict';
const assert=require('node:assert/strict');
const performanceFixture=revision=>{const as_of=new Date().toISOString();return {status:'READY_RECONCILED_NO_EXTERNAL_FLOW',account_revision:revision,as_of,current_equity:'100',valuation_snapshot:{status:'READY',account_revision:revision,valued_at:as_of,strategy_total:'100',market_value:'0',holdings:[]}};};
const {createController}=require('../web/strategy_account.js');
const response=data=>({ok:true,json:async()=>data});
const account=revision=>({revision,cash:'100',cash_confirmation_valid:true,holdings:[],orders:[],fills:[]});
async function scenario(changeRevision=false,changeDuringPerformance=false){
 let revision='r1',finishValue,finishPerformance,performanceCalls=0;
 const c=createController({automaticValuationEnabled:false,fetchImpl:async url=>{
  if(url.endsWith('/valuation'))return new Promise(resolve=>finishValue=()=>resolve(response({status:'READY',account_revision:'r1',holdings:[],market_value:'0'})));
  if(url.endsWith('/restart-performance')){performanceCalls++;return new Promise(resolve=>finishPerformance=()=>resolve(response(performanceFixture('r1'))));}
  return response({status:'READY',account:account(revision)});
 }});
 await c.load();const pending=c.valuation();
 for(let i=0;i<3;i++)await c.load();
 assert.equal(c.getState().valuationLoading,true,'unchanged polling retains in-flight indicator');
 if(changeRevision){revision='r2';await c.load();}
 finishValue();await new Promise(resolve=>setImmediate(resolve));
 if(changeRevision){await pending;assert.equal(performanceCalls,0);assert.equal(c.getState().valuation,null);assert.equal(c.getState().valuationLoading,false);return;}
 assert.equal(performanceCalls,1,'long valuation reaches performance despite polling');
 if(changeDuringPerformance)revision='r2';
 await c.load();finishPerformance();await pending;
 if(changeDuringPerformance){assert.equal(c.getState().performance,null);assert.equal(c.getState().valuation,null);}
 else{assert.equal(c.getState().performance.account_revision,'r1');await c.load();assert.equal(c.getState().performance.account_revision,'r1');assert(c.getState().valuation);}
 assert.equal(c.getState().valuationLoading,false);
}
(async()=>{await scenario();await scenario(true);await scenario(false,true);console.log('PASS same-revision polling and delayed valuation/performance; changed revision rejected at both stages');})().catch(e=>{console.error(e);process.exitCode=1;});
