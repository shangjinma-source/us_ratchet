'use strict';
const assert=require('node:assert/strict');
const {create}=require('../web/news_scheduled_earnings.js');
const doc={createElement:()=>({})};
const cell=()=>({ownerDocument:doc,children:[],appendChild(n){this.children.push(n);}});
(async()=>{
 let now=Date.parse('2026-11-04T05:00:00Z'),calls=[],timers=new Map(),sequence=0,changes=0;
 const event={ticker:'MRNA',event_kind:'EARNINGS_CALL',eligible_as_new_trigger:false,may_refresh_event_window:false,
  scheduled_at:'2026-11-06T13:00:00Z',observed_at:'2026-11-04T05:00:00Z'};
 let response={status:'CONTEXT_ONLY',events:[event],refresh:{status:'SUCCEEDED'}};
 const controller=create({now:()=>now,onChange:()=>changes++,setTimer:(fn,ms)=>{timers.set(++sequence,{fn,ms});return sequence;},clearTimer:id=>timers.delete(id),
  fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>response};}});
 await controller.load();assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
 let out=cell();controller.render(out,'MRNA');assert.match(out.children[0].textContent,/21:00/);
 out=cell();controller.render(out,'SNDK');assert.equal(out.children.length,0);
 await controller.refresh();assert.equal(calls.length,3);assert.equal(calls[1].options.body,'{}');
 now+=86400001;out=cell();controller.render(out,'MRNA');assert.match(out.children[0].textContent,/未核实/);
 response={status:'REVIEW_REQUIRED',events:[event]};now-=86400001;await controller.load();
 out=cell();controller.render(out,'MRNA');assert.match(out.children[0].textContent,/未核实/);
 controller.dispose();const before=calls.length;await controller.refresh();assert.equal(calls.length,before);assert.equal(timers.size,0);
 let resolve,notified=0;const stale=create({fetch:()=>new Promise(r=>resolve=r),onChange:()=>notified++});
 const pending=stale.load();stale.dispose();resolve({ok:true,json:async()=>({status:'CONTEXT_ONLY',events:[event]})});await pending;assert.equal(notified,0);
 console.log('PASS scheduled UI: read-only load, shared refresh, ticker filter, expiry, conflict, disposal');
})().catch(error=>{console.error(error);process.exitCode=1;});
