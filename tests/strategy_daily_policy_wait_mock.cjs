const assert=require('node:assert/strict');
const ui=require('../web/strategy_daily_controller.js');
const doc={createElement:tag=>({tag,children:[],textContent:'',appendChild(x){this.children.push(x);}})};
const container={ownerDocument:doc,replaceChildren(...xs){this.children=xs;}};
const text=n=>[n.textContent||'',...(n.children||[]).flatMap(text)].join(' ');
for(const reason of ['DOMAIN_POLICY_AUTHORIZATION_TIME','DAILY_TARGET_SELECTOR_PROFILE_MISMATCH','WAIT_NEW_SESSION_EVIDENCE','COMPLETE_MINUTES_REQUIRED']){
 const model={account:{revision:'r',holdings:[]},target:null,daily:null,error:reason,historicalQuotes:{},historicalOrders:{}};
 const view=ui.render(container,model,Date.now());
 assert.match(text(container),/等待/);assert.match(text(container),/暂不生成买卖建议/);
 assert(!text(container).includes('状态未确认'));assert.equal(view.rows.length,0);
}
assert.equal(ui.waitingExplanation('NETWORK'),null);
for(const reason of ['SUPPLEMENT_SNAPSHOT_CHANGED','RISK_SUPPLEMENT_SNAPSHOT_CHANGED',
 'SNAPSHOT_CHANGED_DURING_PREVIEW','TARGET_CHANGED_AFTER_GENERATION','DAILY_UI_SNAPSHOT_CHANGED']){
 assert.match(ui.waitingExplanation(reason),/旧版本/);
 assert.match(ui.waitingExplanation(reason),/无需重复录入新增资金/);
}
console.log('policy time/profile WAIT presentation PASS; unknown failures retained');
