const assert=require('node:assert/strict');
const ui=require('../web/news_investment_review.js');
class Node{constructor(doc){this.ownerDocument=doc;this.children=[];}appendChild(n){this.children.push(n);}replaceChildren(...n){this.children=n;}addEventListener(){}removeEventListener(){}}
const doc={createElement:()=>new Node(doc)};
const state={account:{revision:'r'},target:{target_id:'t',proposal_id:'p'},daily:{status:'READY',account_revision:'r',target_id:'t',proposal_id:'p'}};
const evidence={source_id:'s',source_sha256:'h',source_url:'https://example.test/release',published_at:'2026-10-26T22:00:00Z',observed_at:'2026-10-27T00:00:00Z',discovery_delay_seconds:7200};
const proposal={status:'REVIEW_PROPOSAL_ONLY',original_binding:{account_revision:'r',target_id:'t',proposal_id:'p'},executable:false,orders_created:false,review_valid_until:'2026-10-27T00:05:00Z',review_created_at:'2026-10-27T00:00:30Z',timeliness:{cached:true,analysis_completed_at:'2026-10-26T23:51:00Z',revalidated_at:'2026-10-27T00:00:30Z'},rows:[{security_id:'A',action:'KEEP',evidence:[{...evidence,quote:'First quote'},{...evidence,quote:'Second quote'},{...evidence,quote:'First quote'}]}]};
(async()=>{
 const app=ui.mount(new Node(doc),{now:()=>Date.parse('2026-10-27T00:01:00Z'),setTimer:()=>1,clearTimer:()=>{},fetch:async()=>({ok:true,json:async()=>({status:'COMPLETE',proposal})})});
 app.update(state);await app.start();
 const flatten=n=>[n,...n.children.flatMap(flatten)];const nodes=flatten(app.elements.body);const text=nodes.map(n=>n.textContent||'').join(' ');
 assert.match(text,/复用此前分析/);assert.match(text,/本次采集/);assert.match(text,/本次重新校验/);assert.doesNotMatch(text,/发现延迟| · 发现 /);
 assert.equal(nodes.filter(n=>n.href==='https://example.test/release').length,1);
 assert.equal(nodes.filter(n=>n.textContent==='First quote').length,1);assert.equal(nodes.filter(n=>n.textContent==='Second quote').length,1);
 assert.equal(ui.evidenceGroups([{source_id:'s',source_sha256:'1'},{source_id:'s',source_sha256:'2'}]).length,2);
 app.dispose();console.log('r19 cached semantics and evidence dedup: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
