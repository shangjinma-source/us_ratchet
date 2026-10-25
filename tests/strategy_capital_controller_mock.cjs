'use strict';
const assert=require('node:assert/strict');
const {createController,browserPendingStore}=require('../web/strategy_capital_controller.js');
const account={revision:'a'.repeat(64),cash_confirmation_valid:true,available_cash:'1000'};
const target={target_id:'b'.repeat(64)};
function setup(handler,snapshot=()=>({account,target})){
 let stored=null;const calls=[];
 const pendingStore={read:()=>structuredClone(stored),write:v=>{stored=structuredClone(v);},clear:()=>{stored=null;}};
 const build=()=>createController({request:async(path,body)=>{
  calls.push({path,body:structuredClone(body)});return {event_id:body.event_id,...await handler(path,body)};
 },readSnapshot:async()=>snapshot(),eventId:()=> 'capital-unique-1',pendingStore});
 return {build,calls,pendingStore};
}
(async()=>{
 let configure=0;
 const a=setup(async path=>{
  if(path.endsWith('/arrive'))return {status:'INTENT_RECORDED'};
  configure++;return {status:'CONSUMED_BY_PUBLISHED_TARGET',target_id:'new'};
 });
 await a.build().start('250');
 assert.equal(configure,1);assert.equal(a.calls[0].body.contribution_amount,'250');
 assert(!a.calls.some(x=>x.path.includes('cash')));assert.equal(account.available_cash,'1000');
 assert.equal(a.pendingStore.read(),null);
 let phase=0;
 const b=setup(async path=>{
  if(path.endsWith('/arrive')){if(phase++===0)throw Error('NETWORK');return {status:'INTENT_RECORDED'};}
  if(path.endsWith('/status'))return {status:'NOT_FOUND'};
  return {status:'CONSUMED_BY_PUBLISHED_TARGET',target_id:'new'};
 });
 await b.build().start('250');await b.build().resume();
 const records=b.calls.filter(x=>x.path.endsWith('/arrive'));assert.deepEqual(records[0].body,records[1].body);
 const c=setup(async path=>{
  if(path.endsWith('/arrive'))return {status:'INTENT_RECORDED'};
  if(path.endsWith('/configure'))throw Error('NETWORK');
  if(path.endsWith('/status'))return {status:'PREPARED_PUBLISH_ONLY'};
  return {status:'CONSUMED_BY_PUBLISHED_TARGET',target_id:'new'};
 });
 await c.build().start('250');await c.build().resume();
 assert.equal(c.calls.filter(x=>x.path.endsWith('/configure')).length,1);
 assert.equal(c.calls.filter(x=>x.path.endsWith('/recover-publication')).length,1);
 const d=setup(async path=>{
  if(path.endsWith('/arrive'))return {status:'INTENT_RECORDED'};
  if(path.endsWith('/configure'))throw Error('NETWORK');
  return {status:'RECOVERY_REQUIRED'};
 });
 const dc=d.build();await dc.start('250');await dc.resume();await dc.start('300');
 assert.equal(d.calls.filter(x=>x.path.endsWith('/configure')).length,1);
 assert.equal(d.calls.filter(x=>x.path.endsWith('/arrive')).length,1);
 assert.equal(d.pendingStore.read().contribution_amount,'250');
 let changed=false;
 const e=setup(async path=>{
  if(path.endsWith('/arrive')){changed=true;throw Error('CAPITAL_STALE_SNAPSHOT');}
  return {status:'NOT_FOUND'};
 },()=>({account:changed?{...account,revision:'c'.repeat(64)}:account,target}));
 const ec=e.build();await ec.start('250');await ec.resume();
 assert.equal(ec.getState().status,'INTENT_NOT_RECORDED_REFRESH_REQUIRED');
 assert.equal(e.pendingStore.read(),null);
 assert.equal(e.calls.filter(x=>x.path.endsWith('/status')).length,2);
 const f=setup(async()=>({event_id:'other-event',status:'CONSUMED_BY_PUBLISHED_TARGET',target_id:'other'}));
 const fc=f.build();await fc.start('250');
 assert.equal(fc.getState().error,'CAPITAL_RESPONSE_EVENT_MISMATCH');
 assert(f.pendingStore.read());
 const local=new Map(),storage={getItem:k=>local.get(k)??null,setItem:(k,v)=>local.set(k,v),removeItem:k=>local.delete(k)};
 const store=browserPendingStore(storage,'account-1');
 assert.equal(store.read(),null);
 store.write(d.pendingStore.read());assert.deepEqual(browserPendingStore(storage,'account-1').read(),d.pendingStore.read());
 storage.setItem('account-1','broken');assert.throws(()=>store.read());
 assert.equal(storage.getItem('account-1'),'broken'); // Preserve corrupt pending evidence.
 assert.throws(()=>store.write({...d.pendingStore.read(),contribution_amount:'9'.repeat(2500)}));
 assert.equal(storage.getItem('account-1'),'broken');
 console.log('6 capital controller flows PASS: server-only cash credit, same-event retry, publication-only recovery, no reselection, absent-stale recovery, event binding');
})().catch(e=>{console.error(e);process.exitCode=1;});
