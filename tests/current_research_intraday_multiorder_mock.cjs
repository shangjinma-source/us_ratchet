const assert=require('node:assert/strict');
const {validate,eventFor,money,create}=require('../web/current_research_intraday_multiorder.js');
const view={schema:'INTRADAY_MULTIORDER_ACCOUNT_VIEW_V1',research_only:true,execution_blocked:true,real_account:false,price_is_current_quote:false,account_id:'isolated',revision:'a'.repeat(64),original_acceptance_id:'b'.repeat(64),retarget_acceptance_id:'c'.repeat(64),target_month:'2026-10',initial_cash:'1000',cash:'799',reserved_cash:'60',available_cash:'739',fees:'1',recorded_buy_notional:'300',recorded_sell_notional:'100',positions:[{security_id:'A',ticker:'AAA',quantity:10,reserved_quantity:3,available_quantity:7,target_quantity:7,remaining_difference:-3},{security_id:'B',ticker:'BBB',quantity:2,reserved_quantity:0,available_quantity:2,target_quantity:8,remaining_difference:6}],orders:[{order_id:'sell',security_id:'A',ticker:'AAA',side:'SELL',quantity:5,filled_quantity:2,remaining_quantity:3,limit_price:'20',accepted_at:'2026-10-15T14:00:00Z',session_close:'2026-10-15T20:00:00Z',time_in_force:'DAY',closed:null,status:'OPEN',price_is_current_quote:false},{order_id:'buy',security_id:'B',ticker:'BBB',side:'BUY',quantity:8,filled_quantity:2,remaining_quantity:6,limit_price:'10',accepted_at:'2026-10-15T14:00:00Z',session_close:'2026-10-15T20:00:00Z',time_in_force:'DAY',closed:null,status:'OPEN',price_is_current_quote:false}],events:[],event_count:0,has_more_events:false,fee_scope:{commission:'0',other_fees:'UNKNOWN_NOT_RESERVED'}};
const binding=Object.fromEntries(['account_id','revision','original_acceptance_id','retarget_acceptance_id','target_month'].map(k=>[k,view[k]]));
assert.deepEqual(validate(view,binding),view);assert.equal(money('900719925474099312345/100'),'9007199254740993123.45');assert.equal(money('1/3'),'0.33');
for(const edit of [v=>v.cash='800',v=>v.available_cash='740',v=>v.positions[0].reserved_quantity=4,v=>v.orders[0].ticker='OTHER',v=>v.orders.push({...v.orders[0]}),v=>v.real_account=true,v=>v.orders[1].quantity=true,v=>v.raw_blob='secret',v=>v.events=[{files:[]}],v=>v.proposal={reference_valid_until:'2000-01-01T00:00:00Z'}]){const bad=structuredClone(view);edit(bad);assert.throws(()=>validate(bad,binding));}
assert.throws(()=>validate(view,{...binding,account_id:'other'}));assert.throws(()=>validate(view,{...binding,revision:'d'.repeat(64)}));
const now=Date.parse('2026-10-15T15:00:00Z'),values={quantity:'1',price:'9',fees:'1',time:'2026-10-15T22:30:00'};
const buy=eventFor(view,'buy','FILL',values,()=> 'event',now);assert.equal(buy.event.order_id,'buy');assert.equal(buy.event.executed_at,'2026-10-15T22:30:00+08:00');assert(!('side' in buy.event));assert(!('recorded_at' in buy.event));
assert.equal(eventFor(view,'buy','FILL',{...values,time:'2026-10-15T22:30'},()=> 'minute',now).event.executed_at,'2026-10-15T22:30:00+08:00');assert.equal(eventFor(view,'buy','FILL',{...values,time:'2026-10-15T22:30:07'},()=> 'seconds',now).event.executed_at,'2026-10-15T22:30:07+08:00');assert.throws(()=>eventFor(view,'buy','FILL',{...values,time:'2026-02-30T22:30'},()=> 'invalid',now));
assert.throws(()=>eventFor(view,'sell','FILL',values,()=> 'event',now));assert.equal(eventFor(view,'sell','FILL',{...values,price:'21'},()=> 'event',now).event.price,'21');
for(const fields of [{quantity:'7'},{fees:''},{fees:'1000'},{price:'11'},{price:'1/0'},{time:'2026-02-30T22:30:00'}])assert.throws(()=>eventFor(view,'buy','FILL',{...values,...fields},()=> 'event',now));
assert.throws(()=>eventFor(view,'sell','EXPIRE',{},()=> 'event',now));assert.equal(eventFor(view,'sell','EXPIRE',{},()=> 'event',Date.parse('2026-10-15T20:00:00Z')).event.kind,'EXPIRE');
let html='';const container={set innerHTML(x){html=x;},get innerHTML(){return html;},querySelectorAll(){return[];}};const component=create(container);component.setAccount(view,binding);assert.match(html,/封存限价，不是当前行情/);assert.match(html,/AAA/);assert.match(html,/BBB/);assert.doesNotMatch(html,/data-action=/);component.invalidate();assert.doesNotMatch(html,/AAA/);
console.log('PASS multiorder standalone: exact cash/positions/reserves, identities, BUY/SELL order events, fees/times, proposal rejection, default readonly');

(async()=>{
 let buttons={},text='',requests=[],resolve,reject;
 const fields={order:'buy',quantity:'1',price:'9',fees:'1',time:'2026-10-15T22:30:00'};
 const box={set innerHTML(v){text=v;buttons={};for(const match of v.matchAll(/data-action="([^"]+)"/g))buttons[match[1]]={dataset:{action:match[1]},addEventListener(k,f){this.click=f;}};},querySelectorAll(){return Object.values(buttons);},querySelector(s){return{value:fields[s.match(/name="([^"]+)"/)[1]]};}};
 const c=create(box,{now:()=>now,uuid:()=> 'unique-event',onEvent:r=>{requests.push(r);return new Promise((yes,no)=>{resolve=yes;reject=no;});}});
 c.setAccount(view,binding);assert.match(text,/<option value="sell">AAA SELL/);assert.match(text,/<option value="buy">BBB BUY/);
 buttons.FILL.click();buttons.FILL.click();assert.equal(requests.length,1);reject(Error('lost'));
 await new Promise(r=>setImmediate(r));buttons.RETRY.click();assert.deepEqual(requests[1],requests[0]);
 c.invalidate();resolve();await new Promise(r=>setImmediate(r));assert.doesNotMatch(text,/AAA|请求已完成/);
 console.log('PASS multiorder callback: all open orders selectable, doubleclick guard, same-event retry, invalidation late-response guard');
})().catch(e=>{console.error(e);process.exitCode=1;});

{
 let html='',buttons={},inputs={};const box={set innerHTML(v){html=v;buttons={};inputs={};for(const k of ['order','quantity','price','fees','time'])if(v.includes('name="'+k+'"'))inputs[k]={value:k==='order'?'sell':''};for(const match of v.matchAll(/data-action="([^"]+)"/g))buttons[match[1]]={dataset:{action:match[1]},addEventListener(k,f){this.click=f;}};},querySelectorAll(){return Object.values(buttons);},querySelector(s){return inputs[s.match(/name="([^"]+)"/)[1]]||null;}};
 const c=create(box,{now:()=>now,onEvent:()=>{throw Error('invalid form must not submit');}});c.setAccount(view,binding);
 for(const [k,v]of Object.entries({order:'buy',quantity:'1',price:'9',fees:'1',time:'2026-02-30T22:30'}))inputs[k].value=v;
 buttons.FILL.click();assert.match(html,/日期无效/);assert.equal(inputs.order.value,'buy');assert.equal(inputs.quantity.value,'1');assert.equal(inputs.price.value,'9');assert.equal(inputs.fees.value,'1');assert.equal(inputs.time.value,'2026-02-30T22:30');
 c.setAccount(view,binding);assert.equal(inputs.quantity.value,'');assert.equal(inputs.time.value,'');c.invalidate();assert.deepEqual(inputs,{});
 console.log('PASS multiorder form: invalid field preserves all draft values; verified refresh/invalidate clears draft');
}
