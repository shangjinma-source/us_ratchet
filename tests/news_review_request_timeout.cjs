const assert=require('node:assert/strict');
const ui=require('../docs/candidates/news_investment_review_timeout.js');
const {Node,doc}=require('./news_mock_dom.cjs');
const now=Date.parse('2026-10-27T00:01:00Z');
const state={account:{revision:'r',holdings:[]},target:{target_id:'t',proposal_id:'p'},daily:{status:'READY',account_revision:'r',target_id:'t',proposal_id:'p',reference_quotes:{A:{sell:10}}}};
const settle=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};
function harness(mode){
 let id=0,posts=0,signal,late;const timers=new Map();
 const view=ui.mount(new Node(doc),{now:()=>now,requestTimeoutMs:50,
  setTimer:(fn,ms)=>{timers.set(++id,{fn,ms});return id;},clearTimer:key=>timers.delete(key),
  fetch:async(url,options)=>{
   if(url==='/api/news/events/status')return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};
   if(options.method==='POST')posts++;
   signal=options.signal;
   if(mode==='body')return {ok:true,json:()=>new Promise(resolve=>{late=resolve;})};
   if(mode==='poll'&&options.method==='POST')return {ok:true,json:async()=>({status:'RUNNING',job_id:'job'})};
   return new Promise(resolve=>{late=resolve;});
  }});
 view.update(state);
 return {view,timers,get posts(){return posts;},get signal(){return signal;},finish:()=>late?.({ok:true,json:async()=>({status:'COMPLETE',proposal:{}})})};
}
(async()=>{
 for(const mode of ['fetch','body','poll']){
  const h=harness(mode);await settle();const work=h.view.start();await settle();
  let pollWork;
  if(mode==='poll'){await work;pollWork=[...h.timers.values()].find(t=>t.ms===2000).fn();await settle();}
  const deadline=[...h.timers.values()].find(t=>t.ms===50);assert.ok(deadline);deadline.fn();await settle();await work;
  await pollWork;
  assert.equal(h.signal.aborted,true);assert.equal(h.view.isBusy(),false);assert.equal(h.posts,1);
  assert.match(h.view.elements.status.textContent,/未确认/);
  h.finish();await settle();assert.equal(h.posts,1);assert.equal(h.view.isBusy(),false);h.view.dispose();
 }
 const h=harness('fetch');await settle();const work=h.view.start();await settle();h.view.dispose();await work;
 assert.equal(h.signal.aborted,true);assert.equal(h.timers.size,0);assert.equal(h.posts,1);
 console.log('AI request timeout: fetch, body, poll, disposal, late response PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
