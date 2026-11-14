const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_roa_mount.js');
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';}
 appendChild(n){n.parentNode=this;this.children.push(n);return n;}
 replaceChildren(...nodes){this.children=[];for(const n of nodes)this.appendChild(n);}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
 removeEventListener(type,fn){this.listeners[type]=(this.listeners[type]||[]).filter(x=>x!==fn);}
 dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);return true;}
 dispatch(type){for(const fn of this.listeners[type]||[])fn({preventDefault(){}});}
}
const doc=new Node('document',null);doc.createElement=tag=>new Node(tag,doc);doc.defaultView=new Node('window',doc);doc.visibilityState='visible';
const text=n=>[n.textContent||'',...n.children.map(text)].join(' ');
const actions=n=>[n.tag==='strong'?(n.textContent||''):'',...n.children.map(actions)].join(' ');
(async()=>{
 let event=null,rowReason=null;
 let time=Date.parse('2026-11-06T14:31:00Z'),mode='PENDING_OPEN',pending=null,writeCount=0,timer;
 const account={revision:'a'.repeat(64),cash_confirmation_valid:true,available_cash:'100001/100',holdings:[]};
 const request=async(path,body)=>{
  if(path.endsWith('cash-save-and-preview'))writeCount++;
  return {strategy_kind:'ROA_DEFENSIVE_V1',strategy_epoch:'test',account_revision:account.revision,account,
   execution_event:event,market_signal:{risk_on:false,signal_date:'2026-11-06',execution_session:'2026-11-09'},
   status:mode,late_execution:mode==='READY',limit_reference:'SESSION_OPEN',phase:'OPEN',executable:mode==='READY',advice_ready:true,cash_saved:body?true:undefined,
   target_id:'b'.repeat(64),proposal_id:'c'.repeat(64),valid_from:'2026-11-06T14:30:00Z',valid_until:'2026-11-06T21:00:00Z',quote_valid_until:'2026-11-06T14:32:00Z',
   rows:[{security_id:'A',ticker:'AAA',held:0,target_quantity:mode==='READY'?5:null,side:'BUY',quantity:5,limit_price:'100',price_context:{reference_kind:'SESSION_OPEN',reference_price:'100',reference_at:'2026-11-06T14:30:00Z',latest_price:'95',latest_at:'2026-11-06T14:31:00Z'},reason:rowReason||(mode==='HOLD'?'HOLD':'阶段测试')}]};
 };
 const container=new Node('div',doc);
 const app=mount(container,{request,readAccount:async()=>account,eventId:()=>String(writeCount),expectedEpoch:'test',now:()=>time,
  pendingStore:{read:()=>pending,write:x=>pending=x,clear:()=>pending=null},setTimer:fn=>{timer=fn;return 1;},clearTimer:()=>{timer=null;}});
 await app.ready;
 assert.equal(app.elements.input.value,'1000.01');
 assert.ok(text(container).includes('收盘信号：防御持币'));
 assert.ok(text(container).includes('不代表已成交'));
 assert.ok(text(container).includes('等待开盘'));assert.ok(!actions(container).includes('买入 5 股'));assert.equal(writeCount,0);
 mode='READY';app.elements.input.value='1000';app.elements.form.dispatch('submit');await app.whenIdle();
 assert.equal(writeCount,1);assert.ok(!text(container).includes('等待策略数据'));assert.ok(text(container).includes('目标及限价参考今日开盘价'));assert.ok(text(container).includes('买入 5 股'));assert.ok(text(container).includes('$100.00'));
 assert.ok(text(container).includes('限价参考：当日开盘'));assert.ok(text(container).includes('限价较报价 +5.26%'));
 time=Date.parse('2026-11-06T14:32:00Z');timer();
 assert.ok(!text(container).includes('限价较报价'));
 assert.ok(!actions(container).includes('买入 5 股'));assert.ok(text(container).includes('报价已过期'));
 assert.ok(text(container).includes('上次结果（仅供参考）：买入 5 股 · 限价 $100.00'));
 assert.ok(text(container).includes('已过期 0 秒'));
 mode='HOLD';await app.refresh();
 assert.ok(text(container).includes('无需操作'));assert.ok(!actions(container).includes('买入 5 股'));
 assert.ok(!text(container).includes('已过期'));assert.ok(!text(container).includes('需刷新确认'));
 assert.ok(!text(container).includes('上次结果'));assert.equal(timer,null);
 mode='WAIT_CASH_CONFIRMATION';await app.refresh();
 assert.ok(text(container).includes('成交后请填写券商最新可用现金'));
 assert.ok(text(container).includes('上次结果（仅供参考）'));assert.ok(text(container).includes('已过期'));
 assert.ok(!actions(container).includes('买入 5 股'));
 mode='WAIT_ACCOUNT_RESERVATIONS';await app.refresh();
 assert.ok(text(container).includes('挂单占用与现金不一致'));
 assert.ok(!actions(container).includes('买入 5 股'));
 mode='MISSED';event={session:'2026-11-06',signal_date:'2026-11-05',phase:'OPEN'};await app.refresh();
 assert.ok(text(container).includes('2026-11-06 历史执行计划'));
 assert.ok(!text(container).includes('2026-11-09 执行计划'));
 assert.ok(text(container).includes('2026-11-06 最新收盘信号'));
 assert.ok(!actions(container).includes('买入 5 股'));
 rowReason='MISSED_RISK_EXIT';await app.refresh();
 assert.ok(text(container).includes('风险退出尚未完成'));assert.ok(text(container).includes('旧限价不可直接沿用'));
 assert.ok(!actions(container).includes('买入 5 股'));
 app.dispose();console.log('PASS: pre-open plan, one cash button, actionable row, expiry redraw');
})().catch(e=>{console.error(e);process.exitCode=1;});
