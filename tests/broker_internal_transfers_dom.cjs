const assert=require('node:assert/strict');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.value='';this.textContent='';this.disabled=false;}
 append(...nodes){this.children.push(...nodes);if(this.tag==='select'&&!this.value)this.value=nodes[0]?.value||'';}
 replaceChildren(...nodes){this.children=[];this.value='';this.append(...nodes);}
}
global.document={createElement:tag=>new Element(tag)};
const {mount}=require('../web/broker_internal_transfers.js');
(async()=>{
 let events=[],revision='a'.repeat(64),writes=0,id=0,failResponse=true,failRead=false;
 const snapshot=()=>({state:{revision,events},summary:{transfers:events.length?{t:{source:'HSBC',destination:'USMART',principal:'600.25',received:'0',in_transit:'600.25',status:'IN_TRANSIT',sent_at:'2026-11-14T00:00:00Z'}}:{},in_transit_usd:events.length?'600.25':'0',confirmed_fees_usd:events.length?'1.88':'0'}});
 const send=async(path,body)=>{
  assert.equal(path,'/api/strategy-account/internal-transfers');
  if(!body){if(failRead)throw Error('network');return snapshot()}
  writes++;assert.equal(body.event.principal,'600.25');
  if(!events.length){events.push(Object.fromEntries(Object.entries(body.event).sort()));revision='b'.repeat(64)}
  else assert.equal(body.event.event_id,events[0].event_id);
  if(failResponse)throw Error('network');return snapshot();
 };
 const app=mount({container:new Element('div'),send,uuid:()=>String(++id)});await app.ready;
 const e=app.elements;assert.equal(e.panel.tag,'details');
 e.amount.value='600.25';e.fee.value='1.88';e.at.value='2026-11-14T00:00:00';
 await e.form.onsubmit({preventDefault(){}});
 assert.equal(writes,1);assert.match(e.status.textContent,/上次记录已保存/);assert.equal(e.amount.value,'');assert.equal(e.amount.disabled,false);
 // An unconfirmed write disables editing and retries exactly the same event.
 events=[];await app.reload();e.amount.value='600.25';e.fee.value='1.88';e.at.value='2026-11-14T00:00:00';failRead=true;
 await e.form.onsubmit({preventDefault(){}});const savedId=events[0].event_id;assert.equal(e.amount.disabled,true);
 failRead=false;failResponse=false;await e.form.onsubmit({preventDefault(){}});
 assert.equal(events.length,1);assert.equal(events[0].event_id,savedId);assert.equal(e.amount.disabled,false);
 assert.match(e.status.textContent,/购买力未修改/);
 e.amount.value='-1';e.at.value='2026-11-14T00:00:00';const before=writes;await e.form.onsubmit({preventDefault(){}});assert.equal(writes,before);
 app.dispose();console.log('PASS transfer panel: exact cents, lost response readback, identical retry, no cash endpoint');
})().catch(e=>{console.error(e);process.exitCode=1});
