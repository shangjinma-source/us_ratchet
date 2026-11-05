const assert=require('node:assert/strict');
const ui=require('../web/news_investment_review.js');
const {Node,doc}=require('./news_mock_dom.cjs');
const state={account:{revision:'r',holdings:[]},target:{target_id:'t',proposal_id:'p'},daily:{status:'READY',account_revision:'r',target_id:'t',proposal_id:'p',reference_quotes:{A:{sell:10}}}};
const proposal={status:'REVIEW_PROPOSAL_ONLY',original_binding:{target_id:'t',proposal_id:'p',account_revision:'r'},review_created_at:'2026-10-27T00:00:00Z',review_valid_until:'2026-10-27T00:05:00Z',orders_created:false,executable:false,rows:[{security_id:'A',action:'KEEP',reason:'test',original_target_quantity:2,evidence:[]}]};
(async()=>{for(const terminal of ['FAILED','STALE']){
 let posts=0,monitor;const instance=ui.mount(new Node(doc),{now:()=>Date.parse('2026-10-27T00:01:00Z'),setTimer:(f,ms)=>{if(ms===15000)monitor=f;return 1;},clearTimer:()=>{},fetch:async(url,opt)=>({ok:true,json:async()=>url==='/api/news/events/status'?{enabled:false,status:'DISABLED'}:opt?.method==='POST'?(posts++,{status:'COMPLETE',job_id:'j',proposal}):{status:terminal,job_id:'j',error:terminal==='STALE'?'REFRESH_ACCOUNT_AND_REVIEW':'STALE_ACCOUNT_OR_TARGET'}})});
 instance.update(state);await instance.start();assert.ok(instance.elements.body.children.length);await monitor();assert.equal(instance.elements.body.children.length,0);await instance.start();assert.equal(posts,2);assert.ok(instance.elements.body.children.length);instance.dispose();
}console.log('FAILED/STALE clear old proposal and allow explicit retry: PASS');})().catch(e=>{console.error(e);process.exitCode=1;});
