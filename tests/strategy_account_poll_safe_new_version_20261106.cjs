'use strict';
const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_account.js');
const response=data=>({ok:true,json:async()=>data});
const account=revision=>({revision,cash:'100',cash_confirmation_valid:true,holdings:[],orders:[],fills:[]});
(async()=>{
 let revision='r1',finishOld,finishLatest,finishRead,delayRead=false,values=0;
 const c=createController({automaticValuationEnabled:true,makeId:()=> 'synthetic',fetchImpl:async(url,init)=>{
  if(url.endsWith('/valuation')){values++;if(values===1)return new Promise(r=>finishOld=()=>r(response({status:'READY',account_revision:'r1',holdings:[]})));if(values===3)return new Promise(r=>finishLatest=()=>r(response({status:'READY',account_revision:revision,holdings:[]})));return response({status:'READY',account_revision:revision,holdings:[]});}
  if(url.endsWith('/restart-performance'))return response({status:'READY_RECONCILED_NO_EXTERNAL_FLOW',account_revision:revision});
  if(init.method)revision='r2';
  if(delayRead&&!init.method)return new Promise(r=>finishRead=()=>r(response({status:'READY',account:account(revision)})));
  return response({status:'READY',account:account(revision)});
 }});
 await c.load();const old=c.valuation();await c.confirmCash({amount:'100'});
 assert.equal(values,2,'new revision auto valuation must not coalesce into stale pending');assert.equal(c.getState().valuation.account_revision,'r2');
 finishOld();await old;assert.equal(c.getState().valuation.account_revision,'r2');assert(!c.getState().valuationLoading);
 const value=c.valuation();delayRead=true;const read=c.load();finishLatest();await value;
 finishRead();await read;assert.equal(c.getState().valuation.account_revision,'r2');
 console.log('PASS new-version auto valuation while old pending; same-version pending account read retains valuation');
})().catch(e=>{console.error(e);process.exitCode=1;});
