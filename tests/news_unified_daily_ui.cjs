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
const proposal=()=>({review_id:'review',status:'REVIEW_PROPOSAL_ONLY',executable:false,orders_created:false,review_valid_until:'2026-10-27T17:04:00Z',original_binding:{account_revision:'r',target_id:'t',proposal_id:pid},original_preview:daily('11'),rows:[{security_id:'S',action:'EXIT',reason:'synthetic',reviewed:true,original_target_quantity:2,proposed_target_quantity:0}]});
const deps=()=>({now:()=>now,loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),previewDaily:async()=>daily(),saveCash:async()=>account,generateTarget:async()=>target});
class Node{constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}appendChild(n){n.parentNode=this;this.children.push(n);}replaceChildren(...ns){this.children=[];ns.forEach(n=>this.appendChild(n));}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(x=>x!==f);}}
const doc=new Node('document',null);doc.createElement=t=>new Node(t,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const flat=n=>[n,...n.children.flatMap(flat)];
(async()=>{
 const empty=ui.createController(deps());assert.throws(()=>empty.adoptReviewedPreview({...proposal(),original_binding:{}}),/ACCOUNT_TARGET_REQUIRED/);
 const c=ui.createController(deps());await c.refresh();
 for(const mutation of [p=>p.original_binding.account_revision='wrong',p=>p.original_preview.proposal_id='b'.repeat(64),p=>p.review_valid_until=new Date(now).toISOString(),p=>p.original_preview.reference_quotes.S.reference_valid_until=new Date(now).toISOString(),p=>p.original_preview.risk_monthly_targets.S=3]){
  const p=proposal();mutation(p);assert.throws(()=>c.adoptReviewedPreview(p));assert.equal(c.getState().daily.new_orders[0].limit_price,'10');
 }
 const queued=c.load();assert.throws(()=>c.adoptReviewedPreview(proposal()),/BUSY/);await queued;
 c.adoptReviewedPreview(proposal());assert.equal(c.getState().daily.new_orders[0].limit_price,'11');
 c.invalidate();assert.throws(()=>c.adoptReviewedPreview(proposal()),/BUSY/);
 let timers=new Map(),timerid=0,posts=0,gets=0,eventGets=0,notifications=0,cashWrites=0,clock=now;const host=new Node('div',doc);
 const instance=mount(host,{...deps(),now:()=>clock,saveCash:async()=>{cashWrites++;return account;},onChange:()=>notifications++,setTimer:(f,ms)=>{timers.set(++timerid,{f,ms});return timerid;},clearTimer:id=>timers.delete(id),newsReviewFetch:async(url,options)=>{if(url==='/api/news/events/status'){assert.equal(options,undefined);eventGets++;return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};}options?posts++:gets++;return {ok:true,json:async()=>({status:'COMPLETE',job_id:'j',proposal:proposal()})};}});
 await instance.ready;await instance.refresh();
 const button=flat(host).find(n=>n.textContent==='AI新闻复核');assert.equal(button.disabled,false);
 button.listeners.click[0]();for(let i=0;i<12;i++)await Promise.resolve();
 assert.equal(instance.getState().daily.new_orders[0].limit_price,'11');
 assert.ok(flat(host).some(n=>(n.textContent||'').includes('复核完成')),'review survives top draw');
 assert.equal(flat(host).filter(n=>n.tag==='table').length,1);
 assert.equal(flat(host).filter(n=>n.tag==='h3'&&n.textContent==='AI 投资复核').length,0);
 assert.ok(flat(host).some(n=>n.textContent==='AI 风险方案（研究预览）'));
 assert.ok(flat(host).some(n=>n.textContent==='退出持仓'));
 assert.ok(flat(host).some(n=>n.textContent==='未采用'));
 assert.equal(instance.getState().daily.new_orders[0].side,'BUY','AI EXIT must not become formal SELL');
 instance.elements.input.value='123.45';for(const f of instance.elements.input.listeners.input||[])f();
 const details=flat(host).find(n=>n.tag==='details');assert.equal(details.open,false);
 details.open=true;details.listeners.toggle[0]();
 assert.equal(cashWrites,0);
 const monitors=[...timers.values()].filter(x=>x.ms===15000);assert.ok(monitors.length);assert.equal(eventGets,1);
 const priorNotifications=notifications;for(const monitor of monitors)await monitor.f();assert.equal(notifications,priorNotifications,'same job poll must not notify controller or overwrite top');assert.equal(posts,1);assert.equal(gets,1);assert.equal(instance.getState().daily.new_orders[0].limit_price,'11');
 assert.equal(flat(host).find(n=>n.tag==='details').open,true,'open details retained on repaint');
 assert.equal(instance.elements.input.value,'123.45','unsaved cash draft remains');
 clock=now+241000;const expiry=[...timers.values()].find(x=>x.ms===240000);assert.ok(expiry);expiry.f();
 assert.equal(flat(host).filter(n=>n.tag==='details').length,0,'expired opinion detail removed');
 assert.ok(flat(host).some(n=>(n.textContent||'').includes('复核已过期')));
 assert.equal(cashWrites,0);
 const news=require('../web/news_investment_review.js'),cell=new Node('td',doc);
 news.renderImpactCell(cell,'S',{proposal:{rows:[{security_id:'S',action:'ABSTAIN',reviewed:false,reason:'missing',proposed_target_quantity:0}]}});
 assert.ok(flat(cell).some(n=>(n.textContent||'').includes('证据不足，未作判断')));
 assert.ok(!flat(cell).some(n=>(n.textContent||'').includes('复核目标意见')));
 const oldCell=new Node('td',doc);
 news.renderImpactCell(oldCell,'S',{proposal:{review_valid_until:'2026-10-27T18:00:00Z',review_created_at:'2026-10-27T17:00:00Z',timeliness:{cached:true,analysis_completed_at:'2026-10-27T16:30:00Z',revalidated_at:'2026-10-27T17:00:00Z'},rows:[{security_id:'S',action:'KEEP',reviewed:true,evidence:[{published_at:'2026-10-27T12:00:00Z'}]}]}},new Set(),now);
 assert.ok(flat(oldCell).some(n=>n.textContent==='历史背景，非即时预警'));
 assert.ok(flat(oldCell).some(n=>(n.textContent||'').includes('复用此前分析')&&(n.textContent||'').includes('本次重新校验')));
 assert.match(button.title,/按需.*不持续.*不会修改/);
 instance.dispose();console.log('r21 single table, advisory isolation, expiry clearing, cash draft, details, and r20 handshake: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
