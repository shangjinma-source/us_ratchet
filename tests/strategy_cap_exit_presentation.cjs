const assert=require('node:assert/strict');
const ui=require('../web/strategy_daily_controller.js');
const now=Date.parse('2026-10-23T15:00:00Z');
const model={account:{revision:'r',holdings:[{security_id:'S',ticker:'SNDK',quantity:14}]},
 target:{target_id:'t',targets:[{security_id:'S',ticker:'SNDK',quantity:13}]},
 daily:{status:'READY',policy_id:'MONTHLY_CAP50_EXIT20',account_revision:'r',target_id:'t',
  risk_monthly_targets:{S:10},effective_target_quantities:{S:0},
  daily_gate:{rows:[{security_id:'S',action:'SELL'}]},
  signal_explanations:{S:{policy:'MONTHLY_CAP50_EXIT20',signal_date:'2026-10-22',monthly_target:10,effective_target:0,exited:true}},
  new_orders:[{security_id:'S',side:'SELL',quantity:14,limit_price:'100',reference_valid_until:'2026-10-23T15:02:00Z'}]},
 historicalQuotes:{},historicalOrders:{}};
let result=ui.presentation(model,now);
assert.equal(result.rows[0].monthly_target,10);
assert.equal(result.rows[0].daily_effective_target,0);
assert.match(ui.actionExplanation(result.rows[0],result,model),/本月不再买入/);
assert.doesNotMatch(ui.actionExplanation(result.rows[0],result,model),/均线/);
model.daily.account_revision='old';
result=ui.presentation(model,now);
assert.equal(result.rows[0].monthly_target,13);
assert.equal(result.rows[0].action,'WAIT');
console.log('PASS cap target, exit explanation, stale binding rejection');
