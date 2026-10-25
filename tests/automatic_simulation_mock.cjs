const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync('web/automatic_simulation.js','utf8'),context);
const render=context.AutomaticSimulation.render;
const common={simulation_only:true,real_account:false,initial_cash:'20000'};
assert.match(render({...common,status:'WAITING_FOR_INITIALIZATION'}).html,/尚未建立账户/);
assert.match(render({...common,status:'INITIALIZATION_REQUIRES_REVIEW'}).title,/待核查/);
const order={ticker:'<TEST>',side:'SELL',quantity:3,filled_quantity:1,limit_price:'100/3',session_close:'2026-10-15T16:00:00-04:00',display_status:'AWAITING_VERIFICATION'};
const available={...common,status:'AVAILABLE',target_month:'2026-10',cash:'100/3',reserved_cash:'0',holdings:[],targets:[],pending_operations:['FAILED'],orders:[order],daily:{session:'2026-10-16',decision_status:'NO_DECISION_RECORD',unresolved_order_results:1}};
const view=render(available);
assert.match(view.html,/卖出/);assert.match(view.html,/33.33/);assert.match(view.html,/已过有效期 · 待核验/);
assert(!view.html.includes('<TEST>'));assert(view.html.includes('&lt;TEST&gt;'));
assert.match(view.title,/待核查/);assert.throws(()=>render({...common,status:'UNAVAILABLE'}));
assert.match(view.html,/尚未见当日决策记录/);assert.match(view.html,/无法判断成交/);
assert.match(render({...available,daily:{...available.daily,decision_status:'LATE_NO_NEW_DECISION'}}).html,/错过决策时间/);
assert.throws(()=>render({...available,orders:[{...order,side:'BOGUS'}]}));
for(const data of [{...common,status:'WAITING_FOR_INITIALIZATION'},{...common,status:'INITIALIZATION_REQUIRES_REVIEW'},available]){
 const output=render(data);assert.match(output.title,/旧版本模拟/);assert.match(output.html,/未接入今日建议的50%仓位上限和20%退出规则/);
}
console.log('automatic simulation display PASS');
