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

const settle=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};
(async()=>{
 let posts=0,writes=0,resolveReview;const host=new Node('div',doc);
 const instance=mount(host,{...deps(),setTimer:()=>1,clearTimer:()=>{},saveCash:async()=>{writes++;return account;},newsReviewFetch:async(url,options)=>{
  if(!options)return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};
  assert.equal(url,'/api/news/investment-review');posts++;
  return new Promise(resolve=>{resolveReview=()=>resolve({ok:true,json:async()=>({status:'FAILED'})});});
 }});
 await instance.ready;await instance.refresh();await settle();assert.equal(posts,0,'load and ordinary refresh never start model');
 const form=instance.elements.form,inside=flat(form);assert.equal(inside.filter(n=>n.textContent==='AI新闻复核').length,0,'standalone manual button removed');
 const toggle=inside.find(n=>n.textContent==='开启新事件发现');assert.ok(toggle);assert.equal(toggle.type,'button');assert.equal(inside.filter(n=>n.type==='submit').length,1);
 instance.elements.input.value='100';form.listeners.submit[0]({preventDefault(){}});await instance.whenIdle();await settle();
 assert.equal(posts,1);assert.equal(writes,1);assert.equal(instance.getState().daily.status,'READY');assert.equal(instance.getState().daily.new_orders[0].limit_price,'10','V27 preview visible while AI unresolved');
 form.listeners.submit[0]({preventDefault(){}});await instance.whenIdle();await settle();assert.equal(posts,1,'existing AI in flight does not create second POST');
 resolveReview();await settle();instance.dispose();
 for(const mode of ['WAIT','SAVE_FAILED']){
  let attempted=0;const other=mount(new Node('div',doc),{...deps(),setTimer:()=>1,clearTimer:()=>{},previewDaily:async()=>mode==='WAIT'?{status:'WAIT',reason:'NO_PRICE'}:daily(),saveCash:async()=>{if(mode==='SAVE_FAILED')throw Error('SYNTHETIC_SAVE_FAILURE');return account;},newsReviewFetch:async(url,options)=>{if(options)attempted++;return {ok:true,json:async()=>({enabled:false,status:'DISABLED'})};}});
  await other.ready;other.elements.input.value='100';other.elements.form.listeners.submit[0]({preventDefault(){}});await other.whenIdle();await settle();assert.equal(attempted,0,mode+' must not start AI');other.dispose();
 }
 console.log('PASS cash submit integration: no standalone AI, cash->READY->single asynchronous AI; load/refresh/WAIT/save failure do not invoke; existing flight guarded');
})().catch(e=>{console.error(e);process.exitCode=1;});
