'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');
const {presentation,actionExplanation}=require(path.resolve(process.env.NEWS_CONTROLLER_CANDIDATE||'web/strategy_daily_controller.js'));
const now=Date.parse('2026-10-29T01:00:00Z');
function fixture(){return {account:{revision:'r',holdings:[{security_id:'S',ticker:'S',quantity:4},{security_id:'B',ticker:'B',quantity:0}]},target:{target_id:'t',targets:[{security_id:'S',ticker:'S',quantity:2},{security_id:'B',ticker:'B',quantity:10}]},daily:{status:'READY',account_revision:'r',target_id:'t',policy_id:'MONTHLY_CAP50_EXIT20',risk_monthly_targets:{S:2,B:10},effective_target_quantities:{S:2,B:10},daily_gate:{rows:[{security_id:'S',action:'SELL'},{security_id:'B',action:'BUY'}]},reference_quotes:{S:{reference_valid_until:new Date(now+60000).toISOString()},B:{reference_valid_until:new Date(now-1).toISOString()}},new_orders:[{security_id:'S',side:'SELL',quantity:2,limit_price:'10'},{security_id:'B',side:'BUY',quantity:5,limit_price:'10'}],waiting_cash:[{security_id:'B',quantity:5}],difference:{waiting_cash:[{security_id:'B',quantity:5}]}}};}
// Partially expired response: valid SELL remains usable; expired BUY never reports old cash reason.
let model=fixture(),view=presentation(model,now),row=view.rows.find(x=>x.security_id==='B');
assert.equal(view.status,'READY');assert.equal(row.orders.length,0);assert.equal(view.rows.find(x=>x.security_id==='S').orders.length,1);
assert.match(actionExplanation(row,view,model),/顶部刷新/);assert.doesNotMatch(actionExplanation(row,view,model),/资金到账|更新现金/);
// Whole response expired, binding changed, and in-flight refresh all override stale cash explanation.
for(const kind of ['expired','binding','busy']){
 model=fixture();if(kind==='expired')model.daily.reference_quotes.S.reference_valid_until=new Date(now-1).toISOString();
 if(kind==='binding')model.account.revision='new';if(kind==='busy')model.busy=true;
 view=presentation(model,now);row=view.rows.find(x=>x.security_id==='B');
 assert.equal(row.orders.length,0);assert.match(actionExplanation(row,view,model),/顶部刷新/);
}
// A new valid cash-wait response can retain historical old orders: it must still explain real cash shortage.
model=fixture();model.daily.new_orders=model.daily.new_orders.filter(x=>x.security_id==='S');model.daily.daily_gate.rows[1].action='WAIT';model.daily.daily_gate.rows[1].reason='NO_AVAILABLE_CASH';model.historicalOrders={B:[{side:'BUY',quantity:5}]};
view=presentation(model,now);row=view.rows.find(x=>x.security_id==='B');
assert.match(actionExplanation(row,view,model),/可用现金不足.*未成交卖款/);
// Fresh partial BUY remains a current order and explains remaining cash shortage.
model=fixture();model.daily.reference_quotes.B.reference_valid_until=new Date(now+60000).toISOString();view=presentation(model,now);row=view.rows.find(x=>x.security_id==='B');
assert.equal(row.orders.length,1);assert.match(actionExplanation(row,view,model),/先买 5 股，余 5 股待资金/);
// Explicit refresh error retains its higher-priority failure explanation.
model.error='unexpected_error';view=presentation(model,now);row=view.rows.find(x=>x.security_id==='B');assert.match(actionExplanation(row,view,model),/刷新失败/);
// First load is busy but has no prior advice; never claim a nonexistent previous recommendation expired.
model={account:{revision:'r',holdings:[{security_id:'B',ticker:'B',quantity:0}]},target:null,daily:null,busy:true};
view=presentation(model,now);row=view.rows[0];assert.match(actionExplanation(row,view,model),/等待有效数据和报价/);assert.doesNotMatch(actionExplanation(row,view,model),/上一条|已失效/);
console.log('8 stale explanation / valid cash explanation scenarios PASS');
