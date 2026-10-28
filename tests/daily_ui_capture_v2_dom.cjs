const assert=require('node:assert/strict');
const {captureDailyDom}=require('../scripts/capture_daily_ui_acceptance_v2.cjs');
const text=value=>({textContent:value});
const reason=text('补入 2 股。'),label=text('AI 复核 · 研究预览'),note=text('未复核，不代表无风险');
const ai={firstElementChild:label,children:[label,note]};
const cells=[text('TEST'),{textContent:'0 → 2',querySelector:s=>s==='strong'?text('0 → 2'):null},
 {textContent:'买入 2 股限价 $10.00',querySelectorAll:s=>[text(s==='strong'?'买入 2 股':'限价 $10.00')]},
 {textContent:reason.textContent+label.textContent+note.textContent,firstElementChild:reason,querySelector:()=>ai}];
const row={querySelector:()=>cells[0],querySelectorAll:()=>cells};
const table={querySelectorAll:s=>s==='tr'?[row]:['股票','持仓 → 目标','今日建议','原因与 AI 复核'].map(text)};
const save={textContent:'更新现金并查看建议',disabled:false};
global.document={querySelectorAll:s=>s.endsWith('table')?[table]:[save],getElementById:()=>({disabled:false}),body:{innerText:'Actual DOM'}};
global.window=new Proxy({},{get(){throw Error('HIDDEN_APPLICATION_STATE_FORBIDDEN');}});
global.fetch=()=>{throw Error('NETWORK_FORBIDDEN');};
const result=captureDailyDom();
assert.equal(result.dom_rows[0].dom_parts.reason,'补入 2 股。');
assert.deepEqual(result.dom_rows[0].dom_parts.limits,['限价 $10.00']);
assert.equal(result.ui_controls.cash_button_disabled,false);
assert.equal(result.scope,'READ_ONLY_PAGE_CAPTURE');
for(const key of ['state','api_state','account_before','account_after','cash_posts_intercepted','unexpected_writes'])assert.equal(key in result,false,key+' cannot be certified by DOM');
save.disabled=true;assert.equal(captureDailyDom().ui_controls.cash_button_disabled,true);
console.log('PASS pure DOM extractor: no hidden application state, no fetch/click/browser launch, financial/write audit supplied separately');
