const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_monthly_target.js');
const account={revision:'r1',cash_confirmation_valid:true,holdings:[],orders:[]};
const target={status:'SAVED_TARGET',target_id:'t1',targets:[],configuration_reason:'EXPLICIT_RECONFIGURE'};
const ok=data=>({ok:true,json:async()=>data});
(async()=>{
 let posts=0,ids=0,failRead=false;const paths=[];
 const c=createController({makeId:()=>String(++ids),fetchImpl:async(url,init)=>{
  paths.push(url);if(init.method){posts++;return {ok:false,json:async()=>({status:'BLOCKED',reason:'DYNAMIC_SOURCE_CHANGED',write_may_have_occurred:true,reconcile_before_retry:true})};}
  if(failRead)throw Error('offline');return ok(url==='/api/strategy-account'?{status:'READY',account}:target);
 }});
 c.setAccount(account);await c.load();await assert.rejects(c.generate('EXPLICIT_RECONFIGURE'));
 assert.equal(posts,1);assert.equal(ids,1);assert(c.getState().reconciliationRequired);assert(c.getState().message.includes('可能已保存'));
 assert.deepEqual(paths.slice(-2),['/api/strategy-account','/api/strategy-account/target']);
 assert.throws(()=>c.generate('EXPLICIT_RECONFIGURE'),/RECONCILIATION_REQUIRED/);assert.equal(ids,1);assert.equal(posts,1);
 failRead=true;await assert.rejects(c.load());assert(c.getState().reconciliationRequired);assert.throws(()=>c.refresh(),/RECONCILIATION_REQUIRED/);
 failRead=false;await c.load();assert(!c.getState().reconciliationRequired);assert.equal(posts,1);assert.equal(ids,1);assert(!c.getState().fresh);
 let saved=0;const cash=createController({saveCash:async()=>{saved++;const e=Error('gate');e.reconcile_before_retry=true;throw e;},fetchImpl:async url=>ok(url==='/api/strategy-account'?{status:'READY',account}:target)});
 cash.setAccount(account);await assert.rejects(cash.configureCash({amount:'10'}));assert(cash.getState().message.includes('可能已保存'));assert(cash.getState().reconciliationRequired);assert.equal(saved,1);
 c.dispose();cash.dispose();console.log('PASS monthly post-gate reconciliation without automatic POST/new ID');
})().catch(e=>{console.error(e);process.exitCode=1});
