const assert=require('node:assert/strict');
const ui=require('../web/news_investment_review.js');
class Node{constructor(doc){this.ownerDocument=doc;this.children=[];this.listeners={};}appendChild(n){this.children.push(n);}replaceChildren(...n){this.children=n;}addEventListener(k,f){this.listeners[k]=f;}removeEventListener(k){delete this.listeners[k];}}
const doc={createElement:()=>new Node(doc)};
const state={account:{revision:'r'},target:{target_id:'t',proposal_id:'p'},daily:{status:'READY',account_revision:'r',target_id:'t',proposal_id:'p'}};
const clock=Date.parse('2026-10-27T00:01:00Z');
const allText=n=>[n.textContent||'',...n.children.map(allText)].join(' ');
(async()=>{
 for(const status of ['WAIT','FAILED','BLOCKED',undefined]){
  const blocked={...state,daily:{...state.daily,status}};
  assert.equal(ui.view(blocked,null,clock).ready,false);
  let calls=0;
  const instance=ui.mount(new Node(doc),{now:()=>clock,fetch:async()=>{calls++;},setTimer:()=>1,clearTimer:()=>{}});
  instance.update(blocked);assert.equal(instance.elements.button.disabled,true);await instance.start();assert.equal(calls,0);instance.dispose();
 }
 for(const status of ['READY','HOLD']) assert.equal(ui.view({...state,daily:{...state.daily,status}},null,clock).ready,true);
 for(const uncertainty of [['原始证据有限','<script>not executable</script>'],[]]){
  const proposal={status:'REVIEW_PROPOSAL_ONLY',original_binding:{target_id:'t',proposal_id:'p',account_revision:'r'},review_created_at:'2026-10-27T00:00:00Z',review_valid_until:'2026-10-27T00:05:00Z',orders_created:false,executable:false,rows:[{security_id:'A',action:'KEEP',uncertainty,evidence:[]}]};
  const instance=ui.mount(new Node(doc),{now:()=>clock,setTimer:()=>1,clearTimer:()=>{},fetch:async()=>({ok:true,json:async()=>({status:'COMPLETE',proposal})})});
  instance.update(state);await instance.start();
  const text=allText(instance.elements.body);assert.match(text,/不确定性：/);
  if(uncertainty.length){assert.ok(text.includes(uncertainty.join('；')));assert.ok(!JSON.stringify(instance.elements.body.children.map(n=>n.innerHTML)).includes('script'));}
  else assert.match(text,/未提供，不能视为没有不确定性/);
  instance.dispose();
 }
 console.log('ready + uncertainty: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
