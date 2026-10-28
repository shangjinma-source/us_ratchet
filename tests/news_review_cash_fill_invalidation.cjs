const assert=require('node:assert/strict');
const ui=require('../web/strategy_daily_controller.js');
const mountModule=(()=>{if(!process.env.NEWS_TEST_MOUNT_CANDIDATE)return require('../web/strategy_daily_mount.js');const Module=require('node:module'),path=require('node:path');const filename=path.resolve(__dirname,'../web/strategy_daily_mount.js'),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));m._compile(require('node:fs').readFileSync(process.env.NEWS_TEST_MOUNT_CANDIDATE,'utf8'),filename);return m.exports;})();
const {mount}=mountModule;
const now=Date.parse('2026-10-27T17:00:00Z'),pid='a'.repeat(64);
const account={revision:'r',cash_confirmation_valid:true,available_cash:'100',holdings:[{security_id:'S',ticker:'S',quantity:1}]};
const target={target_id:'t',proposal_id:pid,server_month:'2026-10',target_month:'2026-10',proposal_targets:[{security_id:'S',ticker:'S',quantity:2}]};
const daily=(price='10')=>({status:'READY',account_revision:'r',target_id:'t',proposal_id:pid,policy_id:'SAVED_FRONTIER_CAP50_EXIT20_V1',risk_monthly_targets:{S:2},risk_valid_from:'2026-10-27T16:00:00Z',risk_valid_until:'2026-10-27T18:00:00Z',effective_target_quantities:{S:2},daily_gate:{rows:[{security_id:'S',action:'BUY',effective_target:2}]},reference_quotes:{S:{buy:price,reference_valid_until:'2026-10-27T17:05:00Z'}},new_orders:[{security_id:'S',side:'BUY',quantity:1,limit_price:price,reference_valid_until:'2026-10-27T17:05:00Z'}]});
const proposal=()=>({review_id:'review',status:'REVIEW_PROPOSAL_ONLY',executable:false,orders_created:false,review_valid_until:'2026-10-27T17:04:00Z',original_binding:{account_revision:'r',target_id:'t',proposal_id:pid},original_preview:daily('11'),rows:[{security_id:'S',action:'EXIT',reason:'synthetic',reviewed:true,original_target_quantity:2,proposed_target_quantity:0}]});
const deps=()=>({now:()=>now,loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),previewDaily:async()=>daily(),saveCash:async()=>account,generateTarget:async()=>target});
class Node{constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}appendChild(n){n.parentNode=this;this.children.push(n);}replaceChildren(...ns){this.children=[];ns.forEach(n=>this.appendChild(n));}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(x=>x!==f);}}
const doc=new Node('document',null);doc.createElement=t=>new Node(t,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const flat=n=>[n,...n.children.flatMap(flat)];
const settle=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function harness(){
 let server=structuredClone(account),serverTarget=structuredClone(target),writes=0,posts=0,gets=0;
 let saveGate=null,reviewGate=null,getGate=null,lastProposal=null;const timers=new Map();let tid=0;
 const host=new Node('div',doc);
 const instance=mount(host,{now:()=>now,loadAccount:async()=>structuredClone(server),loadTarget:async()=>structuredClone(serverTarget),
 previewDaily:async()=>({...daily('12'),account_revision:server.revision,target_id:serverTarget.target_id,proposal_id:serverTarget.proposal_id}),generateTarget:async()=>structuredClone(serverTarget),
 saveCash:async({amount,expected_revision})=>{assert.equal(expected_revision,server.revision);writes++;if(saveGate)await saveGate.promise;server={...server,revision:'cash-'+writes,available_cash:amount};return structuredClone(server);},
 setTimer:(f,ms)=>{timers.set(++tid,{f,ms});return tid;},clearTimer:id=>timers.delete(id),
 newsReviewFetch:async(url,options)=>{if(url==='/api/news/events/status'){assert.equal(options,undefined);return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};}if(options){posts++;lastProposal=proposal();lastProposal.original_binding.account_revision=server.revision;lastProposal.original_binding.target_id=serverTarget.target_id;lastProposal.original_preview.account_revision=server.revision;lastProposal.original_preview.target_id=serverTarget.target_id;const captured=structuredClone(lastProposal);if(reviewGate)await reviewGate.promise;return {ok:true,json:async()=>({status:'COMPLETE',job_id:'j',proposal:captured})};}gets++;const captured=structuredClone(lastProposal);if(getGate)await getGate.promise;return {ok:true,json:async()=>({status:'COMPLETE',job_id:'j',proposal:captured})};}});
 return {host,instance,timers,get writes(){return writes;},get posts(){return posts;},get gets(){return gets;},setSave:d=>saveGate=d,setReview:d=>reviewGate=d,setGet:d=>getGate=d,
 mutate:kind=>{if(kind==='target')serverTarget={...serverTarget,target_id:'new-target'};else server={...server,revision:kind+'-new',holdings:kind==='fill'?[{security_id:'S',ticker:'S',quantity:2}]:server.holdings};},
 click:()=>instance.elements.form.listeners.submit[0]({preventDefault(){}}),
 opinion:()=>flat(host).some(n=>n.textContent==='退出持仓')&&flat(host).some(n=>n.textContent==='未采用')};
}
async function ready(h){await h.instance.ready;await h.instance.refresh();}
async function show(h){h.click();await h.instance.whenIdle();await settle();assert.ok(h.opinion());assert.equal(h.instance.getState().daily.new_orders[0].side,'BUY');}
function edit(h,amount){h.instance.elements.input.value=amount;for(const f of h.instance.elements.input.listeners.input||[])f();}
function submit(h){h.instance.elements.form.listeners.submit[0]({preventDefault(){}});}
(async()=>{
 for(const amount of ['300','50']){
  const h=harness();await ready(h);await show(h);const gate=deferred(),newReview=deferred();h.setSave(gate);h.setReview(newReview);edit(h,amount);submit(h);await settle();
  assert.equal(h.writes,2);assert.equal(h.opinion(),false,'cash save retires opinion while write pending');assert.equal(h.instance.getState().daily,null);
  submit(h);assert.equal(h.writes,2);gate.resolve();await h.instance.whenIdle();await settle();
  assert.equal(h.writes,2);assert.equal(h.instance.elements.input.value,amount);assert.equal(h.instance.getState().daily.account_revision,'cash-2');
  assert.equal(h.instance.getState().daily.new_orders[0].limit_price,'12');assert.equal(h.instance.getState().daily.new_orders[0].side,'BUY');assert.equal(h.opinion(),false);assert.equal(h.posts,2);newReview.resolve();await settle();assert.equal(h.instance.getState().daily.account_revision,'cash-2');h.instance.dispose();
 }
 {
  const h=harness();await ready(h);await show(h);h.mutate('fill');h.instance.invalidate();assert.equal(h.opinion(),false);assert.equal(h.instance.getState().daily,null);
  await h.instance.refresh();assert.equal(h.instance.getState().account.holdings[0].quantity,2);assert.equal(h.writes,1);h.instance.dispose();
 }
 for(const change of ['cash','target','fill']){
  const h=harness();await ready(h);const delayed=deferred();h.setReview(delayed);h.click();await settle();assert.equal(h.posts,1);
  h.mutate(change);h.instance.invalidate();await h.instance.refresh();const fresh=structuredClone(h.instance.getState().daily);
  delayed.resolve();await settle();assert.deepEqual(h.instance.getState().daily,fresh,'late COMPLETE cannot restore preview');assert.equal(h.opinion(),false);assert.equal(h.writes,1);h.instance.dispose();
 }
 {
  const h=harness();await ready(h);await show(h);edit(h,'123.45');const delayed=deferred();h.setGet(delayed);
  const monitors=[...h.timers.values()].filter(x=>x.ms===15000);const monitor=monitors.at(-1);assert.ok(monitor);const pending=monitor.f();await settle();
  h.mutate('fill');h.instance.invalidate();await h.instance.refresh();delayed.resolve();await pending;await settle();
  assert.equal(h.opinion(),false);assert.equal(h.instance.elements.input.value,'123.45');assert.equal(h.instance.getState().daily.account_revision,'fill-new');
  assert.equal(h.posts,1);assert.equal(h.gets,1);assert.equal(h.writes,1);h.instance.dispose();
 }
 console.log('PASS: cash increase/decrease, single write, fill invalidation, pending revision/target/fill, late monitor, draft and order isolation');
 {
  const h=harness();await ready(h);await show(h);h.instance.setCapitalBusy(true);
  try{assert.equal(h.opinion(),false,'capital busy must retire displayed opinion');assert.equal(h.instance.elements.save.disabled,true);h.instance.setCapitalBusy(false);assert.equal(h.opinion(),false,'unlock must not restore old opinion');}finally{h.instance.dispose();}
  const pending=harness();await ready(pending);const gate=deferred();pending.setReview(gate);pending.click();await settle();const original=structuredClone(pending.instance.getState().daily);edit(pending,'123.45');pending.instance.setCapitalBusy(true);gate.resolve();await settle();assert.equal(pending.opinion(),false);assert.deepEqual(pending.instance.getState().daily,original,'late completion during capital lock cannot adopt preview');pending.instance.setCapitalBusy(false);assert.equal(pending.opinion(),false);assert.equal(pending.instance.elements.input.value,'123.45');assert.equal(pending.writes,1);pending.instance.dispose();console.log('PASS: capital lock clears opinion, disables review, rejects late COMPLETE and unlock never resurrects');
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
