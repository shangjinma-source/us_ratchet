const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const filename=path.resolve('web/strategy_roa_mount.js');const m=new Module(filename,module);m.filename=filename;m.paths=module.paths;m._compile(fs.readFileSync(process.env.ROA_MOUNT_OVERRIDE||filename,'utf8'),filename);const {mount}=m.exports;
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}
 appendChild(n){n.parentNode=this;this.children.push(n);return n;}
 replaceChildren(...nodes){this.children=[];for(const n of nodes)this.appendChild(n);}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
 removeEventListener(type,fn){this.listeners[type]=(this.listeners[type]||[]).filter(x=>x!==fn);}
 dispatchEvent(event){this.dispatch(event.type);}
dispatch(type){for(const fn of this.listeners[type]||[])fn({preventDefault(){}});}
}
const doc=new Node('document',null);doc.createElement=tag=>new Node(tag,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const text=n=>[n.textContent||'',...n.children.map(text)].join(' ');
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 // Two different account revisions while an older request is pending coalesce.
 let release,calls=0,writes=0;const result=rev=>({advice_ready:false,status:'WAIT_CASH_CONFIRMATION',reason:'WAIT_CASH_CONFIRMATION',account_revision:rev,account:{revision:rev,holdings:[]},strategy_kind:'ROA_DEFENSIVE_V1',strategy_epoch:'e'});
 const app=mount(new Node('div',doc),{expectedEpoch:'e',readAccount:async()=>null,eventId:()=>'',pendingStore:{read:()=>null,write(){writes++},clear(){}},request:async(p,b)=>{if(b)writes++;calls++;if(calls===1)return new Promise(r=>release=r);return result('r3')}});
 app.accountInvalidated();app.requestAccountReload('r2');app.accountInvalidated();app.requestAccountReload('r3');release(result('r1'));await app.ready;await tick();assert.equal(calls,2);assert.equal(app.getState().account.revision,'r3');assert.equal(writes,0);app.dispose();
 // Failed queued GET does not retry on repeated state draws or same revision.
 let unlock,n=0;const fail=mount(new Node('div',doc),{expectedEpoch:'e',readAccount:async()=>null,eventId:()=>'',pendingStore:{read:()=>null,write(){throw Error('write')},clear(){}},request:async()=>{n++;if(n===1)return new Promise(r=>unlock=r);throw Error('network down')}});
 fail.accountInvalidated();fail.requestAccountReload('r2');unlock(result('r1'));await fail.ready;await tick();assert.equal(n,2);assert.equal(fail.getState().error,'network down');fail.requestAccountReload('r2');doc.defaultView.dispatch('focus');await tick();assert.equal(n,2);fail.dispose();
 // Persisted uncertain cash must never be resent or cleared by queued reload.
 let network=0,clears=0;const saved={expected_revision:'r',event:{event_id:'cash',kind:'CASH_CONFIRM',amount:'10'}};
 const pending=mount(new Node('div',doc),{expectedEpoch:'e',readAccount:async()=>null,eventId:()=>'',pendingStore:{read:()=>saved,write(){writes++},clear(){clears++}},request:async()=>{network++;throw Error('unexpected request')}});
 await pending.ready;pending.requestAccountReload('r2');await tick();assert.equal(network,0);assert.equal(clears,0);assert.equal(pending.getState().error,'CASH_RECONCILIATION_REQUIRED');assert.deepEqual(pending.getState().pending,saved);pending.dispose();
 console.log('two revisions coalesce; failure no loop; uncertain cash never rewritten PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
