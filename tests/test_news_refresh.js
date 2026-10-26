const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const script = fs.readFileSync('web/news.js', 'utf8');
async function scenario(postStatus, jobStatus) {
  const nodes = {}, calls = [];
  function node() { return {disabled:false,childElementCount:0, textContent:'',addEventListener(type, fn){this[type]=fn;},append(){},replaceChildren(){},className:''}; }
  const document = {getElementById(id){ return nodes[id] ||= node(); },createElement:node};
  const context = {document, URL, Date, AbortController, console,
    setTimeout(fn, ms){ if(ms === 3000) queueMicrotask(fn); return 1; }, clearTimeout(){},
    async fetch(url, options){
      calls.push({url,options});
      if(url === '/api/news/refresh') return {status:postStatus,ok:postStatus<400};
      if(url === '/api/news/job') return {status:200,ok:true,json:async()=>({status:jobStatus})};
      return {ok:true,json:async()=>({schema_version:'news-desk-v1',status:'ready',events:[]})};
    }};
  vm.runInNewContext(script,context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls.map(c=>c.url),['/api/news/latest'], 'loading must not analyze');
  await nodes.analyze.click();
  assert.equal(calls.filter(c=>c.options.method==='POST').length,1);
  const post = calls.find(c=>c.url==='/api/news/refresh');
  assert.equal(post.options.body,'{}');assert.equal(post.options.credentials,'same-origin');
  assert.equal(nodes.analyze.disabled,false);
  if(postStatus===202){assert.equal(calls.filter(c=>c.url==='/api/news/job').length,1);assert.equal(calls.filter(c=>c.url==='/api/news/latest').length,2);}
  else assert.equal(calls.filter(c=>c.url==='/api/news/job').length,0);
  return nodes['job-status'].textContent;
}
(async()=>{
  assert.match(await scenario(202,'SUCCEEDED'),/各条分析状态以结果为准/);
  assert.match(await scenario(202,'FAILED'),/失败/);
  assert.match(await scenario(409),/已有分析任务/);
  assert.match(await scenario(429),/冷却期/);
  assert.match(await scenario(500),/未自动重试/);
  console.log('candidate explicit POST, GET-only load, terminal polling, failure and budget tests PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
