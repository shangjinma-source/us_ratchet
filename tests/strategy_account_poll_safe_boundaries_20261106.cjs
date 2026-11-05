'use strict';
const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_account.js');
const response=data=>({ok:true,json:async()=>data});
const account=revision=>({revision,cash:'100',cash_confirmation_valid:true,holdings:[],orders:[],fills:[]});
async function boundary(kind){
 let revision='r1',finish,failed=false,valuationCalls=0,renders=0;
 const c=createController({automaticValuationEnabled:false,makeId:()=> 'synthetic',onRender:()=>renders++,fetchImpl:async (url,init)=>{
  if(url.endsWith('/valuation')){valuationCalls++;if(valuationCalls===1)return new Promise(resolve=>finish=()=>resolve(response({status:'READY',account_revision:'r1',holdings:[]})));return response({status:'READY',account_revision:revision,holdings:[]});}
  if(url.endsWith('/restart-performance'))return response({status:'READY_RECONCILED_NO_EXTERNAL_FLOW',account_revision:revision});
  if(init.method)revision='r2';
  if(failed)throw Error('synthetic read failure');
  return response({status:'READY',account:account(revision)});
 }});
 await c.load();const pending=c.valuation();assert.equal(c.valuation(),pending);
 if(kind==='write')await c.confirmCash({amount:'100'});
 if(kind==='failed'){failed=true;await c.load();assert.equal(c.getState().loaded,false);}
 if(kind==='dispose')c.dispose();
 const before=renders;finish();await pending;
 assert(!c.getState().valuation);assert(!c.getState().performance);assert(!c.getState().valuationLoading);
 if(kind==='dispose'){assert.equal(renders,before);return;}
 failed=false;await c.load();await c.valuation();assert.equal(valuationCalls,2);assert(c.getState().valuation,'subsequent valuation works after promise cleanup');
}
(async()=>{for(const kind of ['write','failed','dispose'])await boundary(kind);console.log('PASS failed read, write invalidation, dispose, duplicate promise and retry cleanup');})().catch(e=>{console.error(e);process.exitCode=1;});
