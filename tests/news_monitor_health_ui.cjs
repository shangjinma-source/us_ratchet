const assert = require('node:assert/strict');
const path = require('node:path');
const ui = require(process.env.NEWS_MONITOR_UI_CANDIDATE_PATH ? path.resolve(process.env.NEWS_MONITOR_UI_CANDIDATE_PATH) : '../web/news_investment_review.js');
class Node {
 constructor(doc) { this.ownerDocument=doc; this.children=[]; }
 appendChild(node) { this.children.push(node); }
 replaceChildren(...nodes) { this.children=nodes; }
 addEventListener() {}
 removeEventListener() {}
}
const doc={createElement:()=>new Node(doc)};
const text=node=>[node.textContent||'',...node.children.map(text)].join(' ');
const now=Date.parse('2026-10-28T13:00:00Z');
const healthy={enabled:true,worker_alive:true,continuous_monitoring:true,status:'NO_NEW_TIMELY_BODY',checked_at:'2026-10-28T12:59:30Z',source_status:[{ticker:'MRNA',status:'LIST_OK'},{ticker:'SNDK',status:'LIST_OK'}]};
async function render(result) {
 const host=new Node(doc), calls=[];
 const app=ui.mount(host,{now:()=>now,setTimer:()=>1,clearTimer:()=>{},fetch:async(url,options)=>{
  calls.push({url,options});return {ok:true,json:async()=>structuredClone(result)};
 }});
 for(let i=0;i<10;i++)await Promise.resolve();
 const output=text(host);app.dispose();
 assert.deepEqual(calls,[{url:'/api/news/events/status',options:undefined}]);
 return output;
}
(async()=>{
 assert.match(await render(healthy),/未发现及时新稿/);
 const dead=await render({...healthy,worker_alive:false,continuous_monitoring:false});
 assert.match(dead,/后台未运行/);assert.doesNotMatch(dead,/未发现及时新稿/);
 const disabled=await render({...healthy,enabled:false,status:'DISABLED'});
 assert.match(disabled,/新事件发现已关闭/);assert.doesNotMatch(disabled,/后台未运行/);
 for(const statuses of [[{ticker:'SNDK',status:'LIST_FAILED_NO_WATERMARK'}],[healthy.source_status[0],{ticker:'SNDK',status:'LIST_FAILED_NO_WATERMARK'}]]){
  const failed=await render({...healthy,source_status:statuses});
  assert.match(failed,/来源检查未完成（SNDK）/);assert.match(failed,/不能确认没有新稿/);assert.doesNotMatch(failed,/未发现及时新稿/);
 }
 const old='2026-10-27T13:00:00Z', stale=await render({...healthy,checked_at:old});
 assert.ok(stale.includes(ui.localTime(old)));assert.match(stale,/距今/);assert.doesNotMatch(stale,/后台未运行/);
 const recovered=await render({...healthy,last_worker_error:{code:'EVENT_WORKER_TICK_FAILED',at:old}});
 assert.match(recovered,/未发现及时新稿/);assert.match(recovered,/曾发生后台错误/);assert.doesNotMatch(recovered,/后台未运行/);
 const unknown=await render({...healthy,worker_alive:undefined,continuous_monitoring:undefined});assert.match(unknown,/后台运行状态未确认/);
 const current=await render({...healthy,last_worker_error:{code:'EVENT_WORKER_TICK_FAILED',at:'2026-10-28T13:00:00Z'}});assert.match(current,/最近检查失败/);assert.doesNotMatch(current,/未发现及时新稿/);
 const partial=await render({...healthy,status:'SOURCE_OPINION_READY',source_status:[healthy.source_status[0],{ticker:'SNDK',status:'LIST_FAILED_NO_WATERMARK'}]});assert.match(partial,/已解释新稿，等待开盘复核/);assert.match(partial,/来源检查未完成（SNDK）/);
 console.log('PASS 10 monitor DOM cases: normal, stopped, disabled, complete/partial source failure, old check timestamp, historical error, absent health; read-only GET only');
})().catch(error=>{console.error(error);process.exitCode=1;});
