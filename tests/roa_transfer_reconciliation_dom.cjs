const assert=require('node:assert/strict');
class Element{constructor(tag){this.tag=tag;this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent=''}append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);if(this.tag==='select'&&!this.value)this.value=n.value}}replaceChildren(...nodes){this.children=[];this.append(...nodes)}remove(){this.parent.children=this.parent.children.filter(x=>x!==this)}}
global.document={createElement:tag=>new Element(tag)};
const api=require('../data/roa_cash_flow/strategy_cash_classification.js');
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const cash={event_id:'cash',before_revision:'before',after_revision:'after',unexplained_net_change:'-605'};
 const review={account_id:'a',account_revision:'account',transfer_revision:'transfer',reconciliation_revision:'journal',baseline_at:'2026-11-14T00:00:00Z',confirmation_times:{cash:'2026-11-14T02:00:00Z'},confirmations:[cash],transfer_events:[{event_id:'sent',kind:'SENT',principal:'600',fee:'5',occurred_at:'2026-11-14T01:00:00Z'}],document:null,status:'RECONCILIATION_REQUIRED'};
 let response={account_id:'a',revision:'account',classifications_sha256:'hash',unresolved:[cash],classified:[],transfer_review:review};let posted=null;
 const container=new Element('root');
 const mounted=api.mount({container,request:async(path,body)=>{if(body){posted={path,body};review.document=body.document;review.status='SAVED_REQUIRES_VALUATION';response={...response,classifications_sha256:'saved',unresolved:[]};}return response;}});
 await tick();const details=container.children[5];assert.equal(details.hidden,false);
 const select=details.children[2].children[0];assert.equal(select.value,''); // No amount-based automatic association.
 select.value='cash';select.onchange();await mounted.refresh();assert.equal(details.children[2].children[0],select);
 await details.children[3].onclick();assert.equal(posted.path,'/api/strategy-account/transfer-reconciliation');assert.deepEqual(posted.body.document.links,{cash:['sent']});assert.equal(posted.body.expected_revision,'journal');assert.equal(posted.body.document.account_revision,'account');
 // A separate unexplained fee uses the same bundle, not the old full-difference API.
 response={...response,unresolved:[{...cash,unexplained_net_change:'-2'}]};await mounted.refresh();
 const panel=container.children[1],entry=panel.children[1].children[0];entry.children[0].value='FEE';entry.children[1].value='2';entry.children[2].value='2026-11-14T01:30:00';
 await panel.children[3].onclick();assert.equal(posted.path,'/api/strategy-account/transfer-reconciliation');assert.deepEqual(posted.body.document.links,{cash:['sent']});assert.equal(posted.body.document.classifications.cash.net_change,'-2');
 mounted.dispose();console.log('Explicit transfer association and residual classification DOM PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
