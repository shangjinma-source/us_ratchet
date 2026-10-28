// Optional candidate modules are injected before mount imports its dependencies.
for(const [env,name] of [['NEWS_CONTROLLER_CANDIDATE','strategy_daily_controller.js'],['NEWS_REVIEW_CANDIDATE','news_investment_review.js']]){
 if(process.env[env]){const actual=require.resolve('../web/'+name),candidate=require(require('node:path').resolve(process.env[env]));require.cache[actual]={id:actual,filename:actual,loaded:true,exports:candidate};}
}
const assert=require('node:assert/strict');
const ui=require('../web/strategy_daily_controller.js');
const {mount}=require('../web/strategy_daily_mount.js');
const now=Date.parse('2026-10-27T17:00:00Z'),pid='a'.repeat(64);
const account={revision:'r',cash_confirmation_valid:true,available_cash:'100',holdings:[{security_id:'S',ticker:'S',quantity:1}]};
const target={target_id:'t',proposal_id:pid,server_month:'2026-10',target_month:'2026-10',proposal_targets:[{security_id:'S',ticker:'S',quantity:2}]};
const daily=(price='10')=>({status:'READY',account_revision:'r',target_id:'t',proposal_id:pid,policy_id:'SAVED_FRONTIER_CAP50_EXIT20_V1',risk_monthly_targets:{S:2},risk_valid_from:'2026-10-27T16:00:00Z',risk_valid_until:'2026-10-27T18:00:00Z',effective_target_quantities:{S:2},daily_gate:{rows:[{security_id:'S',action:'BUY',effective_target:2}]},reference_quotes:{S:{buy:price,reference_valid_until:'2026-10-27T17:05:00Z'}},new_orders:[{security_id:'S',side:'BUY',quantity:1,limit_price:price,reference_valid_until:'2026-10-27T17:05:00Z'}]});
const proposal=()=>({review_id:'review',status:'REVIEW_PROPOSAL_ONLY',executable:false,orders_created:false,review_valid_until:'2026-10-27T17:04:00Z',original_binding:{account_revision:'r',target_id:'t',proposal_id:pid},original_preview:daily('11'),rows:[{security_id:'S',action:'KEEP',reason:'synthetic',reviewed:true,original_target_quantity:2,proposed_target_quantity:2}]});
const deps=()=>({now:()=>now,loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),previewDaily:async()=>daily(),saveCash:async()=>account,generateTarget:async()=>target});
class Node{constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}appendChild(n){n.parentNode=this;this.children.push(n);}replaceChildren(...ns){this.children=[];ns.forEach(n=>this.appendChild(n));}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(x=>x!==f);}}
const doc=new Node('document',null);doc.createElement=t=>new Node(t,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const flat=n=>[n,...n.children.flatMap(flat)];
(async()=>{
 const c=ui.createController(deps());await c.refresh();
 for(const mutation of [p=>p.original_binding.account_revision='wrong',p=>p.original_preview.proposal_id='b'.repeat(64),p=>p.review_valid_until=new Date(now).toISOString(),p=>p.original_preview.reference_quotes.S.reference_valid_until=new Date(now).toISOString(),p=>p.original_preview.risk_monthly_targets.S=3]){
  const p=proposal();mutation(p);assert.throws(()=>c.adoptReviewedPreview(p));assert.equal(c.getState().daily.new_orders[0].limit_price,'10');
 }
 const queued=c.load();assert.throws(()=>c.adoptReviewedPreview(proposal()),/BUSY/);await queued;
 c.adoptReviewedPreview(proposal());assert.equal(c.getState().daily.new_orders[0].limit_price,'11');
 c.invalidate();assert.throws(()=>c.adoptReviewedPreview(proposal()),/BUSY/);
 let timers=new Map(),timerid=0,posts=0,gets=0,eventGets=0,notifications=0;const host=new Node('div',doc);
 const instance=mount(host,{...deps(),onChange:()=>notifications++,setTimer:(f,ms)=>{timers.set(++timerid,{f,ms});return timerid;},clearTimer:id=>timers.delete(id),newsReviewFetch:async(url,options)=>{if(url==='/api/news/events/status'){assert.equal(options,undefined);eventGets++;return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};}options?posts++:gets++;return {ok:true,json:async()=>({status:'COMPLETE',job_id:'j',proposal:proposal()})};}});
 await instance.ready;await instance.refresh();
 assert.equal(flat(host).some(n=>n.textContent==='AI新闻复核'),false);const button=instance.elements.save;assert.equal(button.disabled,false);
 instance.elements.form.listeners.submit[0]({preventDefault(){}});await instance.whenIdle();for(let i=0;i<30;i++)await Promise.resolve();
 assert.equal(instance.getState().daily.new_orders[0].limit_price,'11');
 assert.ok(flat(host).some(n=>(n.textContent||'').includes('复核完成')),'review survives top draw');
 const monitors=[...timers.values()].filter(x=>x.ms===15000);assert.ok(monitors.length);assert.equal(eventGets,1);
 const priorNotifications=notifications;for(const monitor of monitors)await monitor.f();assert.equal(notifications,priorNotifications,'same job poll must not notify controller or overwrite top');assert.equal(posts,1);assert.equal(gets,1);assert.equal(instance.getState().daily.new_orders[0].limit_price,'11');
 instance.dispose();console.log('r20 actual controller+mount+news UI binding/expiry/queued write and handshake: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
