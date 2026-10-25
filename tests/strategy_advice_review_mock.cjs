'use strict';
const assert=require('node:assert/strict');
const {mount,rows}=require('../web/strategy_advice_review.js');
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};}
 appendChild(node){this.children.push(node);}
 replaceChildren(...nodes){this.children=nodes;}
 addEventListener(name,fn){this.listeners[name]=fn;}
 removeEventListener(name){delete this.listeners[name];}
 click(){if(!this.disabled)return this.listeners.click?.();}
}
const doc={createElement:tag=>new Node(tag,doc)};
const text=node=>[node.textContent||'',...node.children.map(text)].join(' ');
const event={event_id:'fixture',generated_at:'2026-10-20T14:00:00Z',generated_status:'READY',
 final_return_status:'WAIT',followup_status:'NOT_ADMITTED',
 new_orders:[{ticker:'SNDK',security_id:'S',side:'SELL',quantity:4,limit_price:'10025/100'}]};
(async()=>{
 const calls=[];let code=200,items=[event],legacy=0;
 const container=new Node('div',doc),view=mount(container,{fetchImpl:async(url,options)=>{
  calls.push({url,options});return {status:code,ok:code===200,json:async()=>({items,next_cursor:items.length?1:0})};
 },onLegacy:()=>legacy++});
 await view.ready;
 assert.match(text(container),/SNDK 卖出 4 \$100.25 返回前已转为等待/);
 assert.match(text(container),/1 \/ 5 \/ 20 日价格跟踪：待接入/);
 assert.equal(text(container).match(/价格跟踪/g).length,1);
 assert.equal(rows([event])[0].executable,false);
 assert.equal(calls[0].url,'/api/strategy-advice-v1/observations?after=0&limit=20');
 assert.equal(calls[0].options.method,'GET');
 view.elements.legacy.click();assert.equal(legacy,1);assert.equal(calls.length,1);
 code=404;await view.refresh();assert.match(text(container),/尚未启用/);
 assert(calls.every(call=>call.url.startsWith('/api/strategy-advice-v1/observations')));
 code=409;await view.refresh();assert.match(text(container),/暂不可用/);
 code=200;items=[{...event,new_orders:[],final_return_status:'HOLD'}];await view.refresh();
 assert(!text(container).includes('价格跟踪'));
 items=[];await view.refresh();assert.match(text(container),/暂无已保存/);
 const count=calls.length;view.dispose();await view.refresh();assert.equal(calls.length,count);
 const ready=rows([{...event,final_return_status:'READY'}])[0];
 assert.equal(ready.executable,false);assert.match(ready.state,/非当前指令/);
 assert.match(rows([{...event,followup_status:'UNKNOWN'}])[0].followup,/无已核验数据/);
 console.log('advice review GET-only/history/404/WAIT/no fabricated followup PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
