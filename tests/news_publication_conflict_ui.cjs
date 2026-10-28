const assert=require('node:assert/strict');
const path=require('node:path');
const ui=require(process.env.NEWS_REVIEW_CANDIDATE?path.resolve(process.env.NEWS_REVIEW_CANDIDATE):'../web/news_investment_review.js');
const {Node,doc}=require('./news_mock_dom.cjs');
(async()=>{
 for(const status of ['WAIT_PUBLICATION_TIME_CONFLICT','SOURCE_OPINION_READY','REVIEW_RUNNING','REVIEW_COMPLETE']){
  const value=ui.publicationConflictText({status,publication_conflicts:[{ticker:'SNDK'}]});
  assert.match(value,/SNDK.*发布时间存在冲突/);assert.match(value,/尚未形成及时 AI 意见/);assert.doesNotMatch(value,/没有风险|安全/);
 }
 const container=new Node(doc),calls=[];
 const mounted=ui.mount(container,{fetch:async(url,options)=>{
  calls.push({url,options});assert.equal(url,'/api/news/events/status');assert.equal(options,undefined);
  return {ok:true,json:async()=>({enabled:true,status:'SOURCE_OPINION_READY',publication_conflicts:[{ticker:'SNDK'}]})};
 },setTimer:()=>1,clearTimer:()=>{}});
 await new Promise(resolve=>setImmediate(resolve));
 const allText=node=>[node.textContent||'',...node.children.map(allText)].join(' ');
 const text=allText(container);
 assert.match(text,/已解释新稿，等待开盘复核/);
 assert.match(text,/SNDK：发布时间存在冲突，尚未形成及时 AI 意见/);
 assert.match(text,/不自动下单/);assert.doesNotMatch(text,/没有风险/);
 assert.equal(calls.length,1);assert.equal(calls.filter(call=>call.options).length,0);
 mounted.dispose();
 console.log('publication conflict UI: PASS actual mount/eventPoll GET-only, mixed state visible; no model or writes');
})().catch(error=>{console.error(error);process.exitCode=1;});
