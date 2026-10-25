const assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {create}=require('../web/current_quantity_v2_intraday.js');
const fixture=JSON.parse(execFileSync('python',['-c',"import sys,json;sys.path.insert(0,'tests');from test_current_quantity_v2_intraday_reference import fixture;s,p,*_=fixture();print(json.dumps({'research':p,'response':s.preview(p['research_id'])}))"],{cwd:require('node:path').join(__dirname,'..'),encoding:'utf8'}));
let now=Date.parse('2026-10-15T12:00:30-04:00'),pending=[],calls=[],timers=new Map(),id=0;
const details={open:false,hidden:true,style:{},addEventListener(k,f){this[k]=f;}},box={innerHTML:'',querySelector:()=>({addEventListener(){}})};
const c=create(details,box,(url,options)=>{calls.push({url,options});return new Promise(r=>pending.push(r));},{now:()=>now,set:(f,n)=>{timers.set(++id,{f,at:now+n});return id;},clear:i=>timers.delete(i)});
const tick=()=>new Promise(r=>setImmediate(r)),respond=(d=fixture.response,ok=true)=>pending.shift()({ok,json:async()=>d});
(async()=>{
 c.setResearch(fixture.research);assert.equal(calls.length,0);details.open=true;details.toggle();c.refresh();assert.equal(calls.length,1);assert.deepEqual(JSON.parse(calls[0].options.body),{research_id:fixture.research.research_id});respond();await tick();assert.match(box.innerHTML,/AAA/);assert.match(box.innerHTML,/BBB/);assert.match(box.innerHTML,/23.00/);assert.match(box.innerHTML,/条件数量 2 股/);
 c.refresh();assert.doesNotMatch(box.innerHTML,/23.00/);respond({},false);await tick();assert.doesNotMatch(box.innerHTML,/23.00/);
 c.refresh();c.invalidate();respond();await tick();assert.equal(details.hidden,true);assert.doesNotMatch(box.innerHTML,/23.00/);assert.equal(timers.size,0);
 c.setResearch({...fixture.research,research_version:'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION'});assert.equal(details.hidden,true);const before=calls.length;c.refresh();assert.equal(calls.length,before);
 c.setResearch(fixture.research);respond();await tick();now+=91000;for(const [i,t]of [...timers])if(t.at<=now){timers.delete(i);t.f();}assert.doesNotMatch(box.innerHTML,/23.00/);assert.match(box.innerHTML,/过期/);
 now=Date.parse('2026-10-15T12:00:30-04:00');
 for(const change of [d=>d.stocks[0].security_id='wrong',d=>d.remaining_cash='99',d=>d.stocks[0].quantity=4,d=>d.stocks[0].refresh_by='2099-01-01',d=>d.research_id='wrong',d=>d.stocks[0].status='UNAVAILABLE']){
  c.refresh();const bad=structuredClone(fixture.response);change(bad);respond(bad);await tick();assert.match(box.innerHTML,/不可用/);assert.doesNotMatch(box.innerHTML,/23.00/);
 }
 c.refresh();details.open=false;details.toggle();respond();await tick();assert.equal(timers.size,0);assert.doesNotMatch(box.innerHTML,/23.00/);
 console.log('PASS V2 intraday: real pure Python fixture, multi-security exact cash, pending/expiry/invalidation/late response, wrong identities/budget/quantity, TOP1 isolation, no network');
})().catch(e=>{console.error(e);process.exitCode=1;});
