const assert=require('node:assert/strict');
const {createController}=require('../docs/candidates/roa_cash_controller_20261106.js');
let clock=Date.parse('2026-11-06T14:31:00Z');
function fixture(request){
 let stored=null,ids=0;
 const pendingStore={read:()=>structuredClone(stored),write:x=>{stored=structuredClone(x);},clear:()=>{stored=null;}};
 const controller=createController({request,readAccount:async()=>({revision:'a'.repeat(64)}),eventId:()=>`cash-${++ids}`,pendingStore,expectedEpoch:'test',now:()=>clock});
 return {controller,pendingStore};
}
const response=()=>({cash_saved:true,advice_ready:true,account_revision:'b'.repeat(64),account:{revision:'b'.repeat(64)},
 advice:{account_revision:'b'.repeat(64),target_id:'c'.repeat(64),proposal_id:'d'.repeat(64),strategy_epoch:'test',executable:false,
 valid_from:'2026-11-06T14:30:00Z',valid_until:'2026-11-06T21:00:00Z',quote_valid_until:'2026-11-06T14:32:00Z'}});
(async()=>{
 const calls=[];let observed=false;
 const first=fixture(async(path,body)=>{
  calls.push({path,body});
  if(path.endsWith('cash-save-and-preview'))throw Error('NETWORK_LOST');
  if(path.endsWith('cash-status'))return {cash_saved:observed?true:null,advice_ready:false,reason:'CASH_NOT_YET_OBSERVED'};
  return response();
 });
 await first.controller.save('1000');
 assert.equal(first.controller.getState().cashSaved,null);
 await first.controller.save('2000');
 assert.equal(calls.length,1);
 await first.controller.refresh();
 assert.equal(calls.length,2);assert.ok(first.pendingStore.read());
 observed=true;await first.controller.refresh();
 assert.equal(first.controller.getState().advice.target_id,'c'.repeat(64));
 assert.equal(first.pendingStore.read(),null);
 assert.equal(calls.filter(x=>x.path.endsWith('cash-save-and-preview')).length,1);
 assert.equal(calls[0].body.event.amount,'1000');
 let release;
 const second=fixture(async()=>new Promise(resolve=>{release=resolve;}));
 const operation=second.controller.save('500');
 await new Promise(resolve=>setImmediate(resolve));
 second.controller.accountInvalidated();release(response());await operation;
 assert.equal(second.controller.getState().advice,null);
 assert.equal(second.controller.getState().cashSaved,true);
 assert.equal(second.controller.getState().error,'ACCOUNT_CHANGED_REFRESH_REQUIRED');
 const third=fixture(async()=>({...response(),advice:{...response().advice,strategy_epoch:'wrong'}}));
 await third.controller.save('0');
 assert.equal(third.controller.getState().advice,null);
 assert.equal(third.controller.getState().error,'ADVICE_SNAPSHOT_MISMATCH');
 clock=Date.parse('2026-11-06T14:32:00Z');
 assert.equal(first.controller.getState().advice,null);
 assert.equal(first.controller.getState().error,'ADVICE_QUOTE_EXPIRED');
 console.log('PASS: uncertain-write reconciliation, no duplicate save, stale response, strategy epoch');
})().catch(error=>{console.error(error);process.exitCode=1;});
