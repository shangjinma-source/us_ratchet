const assert=require('node:assert/strict');
class Element{constructor(tag){this.tag=tag;this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent=''}append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);if(this.tag==='select'&&!this.value)this.value=n.value}}replaceChildren(...nodes){this.children=[];this.append(...nodes)}remove(){this.parent.children=this.parent.children.filter(x=>x!==this)}}
global.document={createElement:tag=>new Element(tag)};
const api=require('../data/roa_cash_flow/strategy_cash_classification.js');
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 assert.match(api.unresolvedSummary([{unexplained_net_change:'-3744.99'},{unexplained_net_change:'3674'},{unexplained_net_change:'-54'},{unexplained_net_change:'-1.33'},{unexplained_net_change:'-178.59'}]), /5 笔.*-304\.91.*不是已确认费用/);
 assert.match(api.unresolvedSummary([{unexplained_net_change:'-1/3'},{unexplained_net_change:'1/3'}]), /0\.00/);
 assert.match(api.unresolvedSummary([{unexplained_net_change:'invalid'}]), /合计待核验/);
 assert.equal(api.dollars('50/1'),'50.00');assert.equal(api.signedAmount('WITHDRAWAL','50','increase'),'-50');assert.equal(api.signedAmount('CORRECTION','5','decrease'),'-5');assert.throws(()=>api.signedAmount('DEPOSIT','-5'));
 const container=new Element('root');let revision='one',fail=false,calls=0;const row={event_id:'event',before_revision:'x',after_revision:'y',unexplained_net_change:'50'};
 const request=async()=>{calls++;if(fail)throw Error('offline');return {account_id:'a',revision,unresolved:[row],profit:null}};
 const mounted=api.mount({container,request});await tick();const panel=container.children[1],items=panel.children[1],save=panel.children[3],recheck=panel.children[4];
 assert.match(container.children[0].textContent,/1 笔资金差额.*50\.00/);
 assert.match(panel.children[0].textContent,/第 1 \/ 1 笔.*并非总差额/);
 assert.equal(panel.hidden,false);items.children[0].children[1].value='50';items.children[0].children[1].oninput();await mounted.refresh();assert.equal(items.children[0].children[1].value,'50');
 revision='two';await mounted.refresh();assert.equal(save.disabled,true);assert.equal(recheck.hidden,false);assert.equal(items.children[0].children[1].value,'50');await recheck.onclick();assert.equal(save.disabled,false);
 fail=true;await mounted.refresh();const before=calls;await save.onclick();assert.equal(calls,before);assert.equal(recheck.hidden,false);assert.equal(container.children[0].textContent,'阶段金额盈亏待核验');fail=false;await recheck.onclick();assert.equal(save.disabled,false);assert.equal(items.children[0].children[1].value,'50');const after=calls;mounted.dispose();await mounted.refresh();assert.equal(calls,after);
 // Inflight completion after dispose must not draw or restart refresh.
 let resolve;const other=new Element('root');const second=api.mount({container:other,request:()=>new Promise(r=>resolve=r)});second.dispose();resolve({revision:'x',unresolved:[row]});await tick();assert.equal(other.children[1].hidden,true);
 const hc=new Element('root');let posted=null,hash='a'.repeat(64);
 const third=api.mount({container:hc,request:async(path,body)=>{if(body)posted=body;return {account_id:'a',revision:'three',unresolved:[],classified:[{...row,document_sha256:hash,classification_state:'REPAIR_REQUIRED',document:{items:[{kind:'UNRECORDED_TRADE',amount:'50',effective_at:'2026-11-06T10:00:00Z'}]}}]}}});await tick();
 assert.equal(hc.children[1].hidden,true);hc.children[3].children[1].children[0].onclick();await tick();const editor=hc.children[1],entry=editor.children[1].children[0];assert.equal(editor.hidden,false);assert.equal(entry.children[1].value,'50.00');entry.children[0].value='DEPOSIT';entry.children[0].onchange();
 hash='b'.repeat(64);await third.refresh();assert.equal(editor.children[3].disabled,true);await editor.children[3].onclick();assert.equal(posted,null);await editor.children[4].onclick();assert.equal(editor.children[1].children[0].children[0].value,'UNRECORDED_TRADE');editor.children[1].children[0].children[0].value='DEPOSIT';await editor.children[3].onclick();assert.equal(posted.expected_document_sha256,hash);assert.equal(posted.document.items[0].kind,'DEPOSIT');third.dispose();
 console.log('DOM candidate checks PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
