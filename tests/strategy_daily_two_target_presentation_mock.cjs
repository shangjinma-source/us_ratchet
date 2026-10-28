// Optional candidate modules are injected before mount imports its dependencies.
for(const [env,name] of [['NEWS_CONTROLLER_CANDIDATE','strategy_daily_controller.js'],['NEWS_REVIEW_CANDIDATE','news_investment_review.js']]){
 if(process.env[env]){const actual=require.resolve('../web/'+name),candidate=require(require('node:path').resolve(process.env[env]));require.cache[actual]={id:actual,filename:actual,loaded:true,exports:candidate};}
}
const assert=require('node:assert/strict');const ui=require('../web/strategy_daily_controller.js');
const now=Date.parse('2026-11-02T15:00:00Z');
const model={account:{revision:'r',holdings:[{security_id:'S',ticker:'SNDK',quantity:14}]},target:{target_id:'t',targets:[{security_id:'S',ticker:'SNDK',quantity:13},{security_id:'M',ticker:'MRNA',quantity:52}]},daily:{policy_id:'MONTHLY_CAP50_EXIT20',risk_monthly_targets:{S:13,M:52},reference_quotes:{S:{security_id:'S',sell:'1300',reference_valid_until:'2026-11-02T15:02:00Z'}},status:'READY',account_revision:'r',target_id:'t',effective_target_quantities:{S:6,M:26},daily_gate:{rows:[{security_id:'S',action:'SELL'},{security_id:'M',action:'WAIT'}]},new_orders:[{security_id:'S',side:'SELL',quantity:8,limit_price:'1300',reference_valid_until:'2026-11-02T15:02:00Z'}]},historicalQuotes:{},historicalOrders:{}};
const rows=ui.presentation(model,now).rows;assert.deepEqual(rows.map(r=>[r.ticker,r.held,r.monthly_target,r.daily_effective_target,r.action]),[['SNDK',14,13,6,'SELL'],['MRNA',0,52,26,'WAIT']]);assert.equal(rows[1].orders.length,0);
const expired=ui.presentation(model,now+120001);assert.equal(expired.rows[0].action,'WAIT');assert.equal(expired.rows[0].historical_orders[0].quantity,8);assert.equal(expired.rows[0].historical_orders[0].executable,false);
console.log('PASS two monthly stocks remain visible: held14/0, monthly13/52, daily6/26, sell8+wait, expiry historical');
const held=structuredClone(model);held.account.holdings=[];held.daily.status='HOLD';held.daily.new_orders=[];
held.daily.effective_target_quantities={S:0};held.daily.daily_gate.rows=[{security_id:'S',action:'HOLD'}];
held.daily.signal_explanations={S:{policy:'MONTHLY_CAP50_EXIT20',signal_date:'2026-10-30',exited:true,monthly_target:13,effective_target:0}};
let display=ui.presentation(held,now);
assert.match(ui.actionExplanation(display.rows[0],display,held),/保持空仓，本月不再买入/);
held.daily.signal_explanations.S.monthly_target=12;
assert.doesNotMatch(ui.actionExplanation(display.rows[0],display,held),/本月不再买入/);
held.busy=true;display=ui.presentation(held,now);assert.equal(display.rows[0].action,'WAIT');
held.busy=false;held.error='DAILY_RESPONSE_UNAVAILABLE';display=ui.presentation(held,now);
assert.equal(display.rows[0].action,'WAIT');assert.match(ui.actionExplanation(display.rows[0],display,held),/返回异常.*建议未更新/);
console.log('PASS exited hold explanation and busy/error hold suppression');

const noQuote=structuredClone(model);noQuote.daily.reference_quotes={};assert.equal(ui.presentation(noQuote,now).rows[0].orders.length,0);assert.equal(ui.presentation(noQuote,now).rows[0].action,"WAIT");
const noPolicy=structuredClone(model);delete noPolicy.daily.risk_monthly_targets;assert.equal(ui.presentation(noPolicy,now).rows[0].monthly_target,null);
console.log("PASS missing quote or risk target evidence is not admitted");
