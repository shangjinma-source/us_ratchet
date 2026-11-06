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
(async()=>{
 let release,calls=0;const account={revision:'old',cash_confirmation_valid:true,available_cash:'100',holdings:[]};
 const app=mount(new Node('div',doc),{expectedEpoch:'e',readAccount:async()=>account,eventId:()=>'',pendingStore:{read:()=>null,write(){},clear(){}},request:async()=>{calls++;if(calls===1)return new Promise(r=>release=r);return {advice_ready:false,status:'WAIT_CASH_CONFIRMATION',reason:'WAIT_CASH_CONFIRMATION',account_revision:'new',account:{...account,revision:'new'},strategy_kind:'ROA_DEFENSIVE_V1',strategy_epoch:'e'};}});
 assert.equal(app.getState().busy,true);app.accountInvalidated();app.requestAccountReload('new');app.requestAccountReload('new');assert.equal(calls,1);
 release({advice_ready:false,status:'WAIT_CASH_CONFIRMATION',reason:'WAIT_CASH_CONFIRMATION',account_revision:'old',account,strategy_kind:'ROA_DEFENSIVE_V1',strategy_epoch:'e'});await app.ready;await new Promise(r=>setImmediate(r));
 assert.equal(calls,2);assert.equal(app.getState().error,'WAIT_CASH_CONFIRMATION');assert.equal(app.getState().account.revision,'new');assert.equal(app.getState().advice,null);
 app.requestAccountReload('new');await new Promise(r=>setImmediate(r));assert.equal(calls,2,'No automatic retry of same revision failure');app.dispose();app.requestAccountReload('later');await new Promise(r=>setImmediate(r));assert.equal(calls,2);console.log('queued revision reload after inflight invalidation PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
