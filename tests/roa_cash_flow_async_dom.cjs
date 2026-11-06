const assert=require('node:assert/strict');
class Element{constructor(tag){this.tag=tag;this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent=''}append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);if(this.tag==='select'&&!this.value)this.value=n.value}}replaceChildren(...nodes){this.children=[];this.append(...nodes)}remove(){this.parent.children=this.parent.children.filter(x=>x!==this)}}
global.document={createElement:tag=>new Element(tag)};
const api=require(process.env.ROA_FLOW_JS_OVERRIDE ? require('node:path').resolve(process.env.ROA_FLOW_JS_OVERRIDE) : '../data/roa_cash_flow/strategy_cash_classification.js');const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 let pending, calls=0,hash='one',revision='r';const node=new Element('root');
 const current=()=>({account_id:'a',revision,classifications_sha256:hash,unresolved:[],classified:[],performance_reason:'VALUATION_PENDING',profit:null});
 const request=async path=>{if(path.endsWith('/profit')){calls++;return new Promise(r=>pending=r)}return current()};
 const ui=api.mount({container:node,request});assert.match(node.children[0].textContent,/读取/);await tick();assert.equal(calls,1);assert.match(node.children[0].textContent,/正在计算/);assert.equal(node.children[3].children[0].textContent,'已记录资金原因');
 await ui.refresh();assert.equal(calls,1);const old=current();hash='two';await ui.refresh();pending({...old,profit:{net_external_flow:'0',profit_amount:'999'},profit_valid_until:new Date(Date.now()+30000).toISOString()});await tick();assert.doesNotMatch(node.children[0].textContent,/999/);
 // Explicit retry is possible after a discarded stale result; no auto retry.
 await tick();assert.equal(calls,2);pending({...current(),performance_reason:'VALUATION_UNAVAILABLE'});await tick();assert.equal(node.children[4].hidden,false);await ui.refresh();assert.equal(calls,2);node.children[4].onclick();assert.equal(calls,3);
 pending({...current(),profit:{net_external_flow:'0',profit_amount:'10'},profit_valid_until:new Date(Date.now()+500).toISOString()});await tick();assert.match(node.children[0].textContent,/10.00/);await ui.refresh();assert.match(node.children[0].textContent,/10.00/);assert.equal(calls,3);await new Promise(r=>setTimeout(r,550));assert.match(node.children[0].textContent,/过期/);assert.equal(calls,3);ui.dispose();
 console.log('async delayed source/revision binding, singleflight, explicit retry, expiry PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
