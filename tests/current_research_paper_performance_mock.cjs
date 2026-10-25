const assert=require('node:assert/strict'),{create}=require('../web/current_research_paper_performance.js');
const binding={account_id:'paper-a',revision:'r1',plan_id:'p1',genesis_research_id:'old'};
const good={...binding,expected_revision:'r1',current_plan_id:'p1',research_only:true,execution_blocked:true,status:'COMPLETE',return_scope:'PRICE_AND_RECORDED_FILL_FEES_ONLY',total_return_certified:false,elapsed_calendar_days:5,recorded_fill_count:1,recorded_fees:'1/2',total_return:'1/10',maximum_close_drawdown:'1/20',start_date:'2026-10-10',through_date:'2026-10-15'};
function setup(){let toggle,calls=[],pending=[];const details={open:false,addEventListener:(k,f)=>toggle=f},body={textContent:'',innerHTML:''};const c=create(details,body,(url,opts)=>{calls.push({url,opts});return new Promise(r=>pending.push(r));},binding);return {details,body,c,calls,open(){details.open=true;toggle();},close(){details.open=false;toggle();},reply(d){pending.shift()({ok:true,json:async()=>d});}};}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
let x=setup();assert.equal(x.calls.length,0);x.open();x.open();assert.equal(x.calls.length,1);x.reply(good);await tick();assert.match(x.body.innerHTML,/10.00%/);assert.match(x.body.innerHTML,/5.00%/);assert.match(x.calls[0].url,/expected_revision=r1/);assert.equal(x.calls[0].opts.body,undefined);
for(const bad of [{...good,genesis_research_id:'newTOP1'},{...good,revision:'r0'},{...good,current_plan_id:'p0'},{...good,account_id:'other'}]){x=setup();x.open();x.reply(bad);await tick();assert.match(x.body.textContent,/不一致/);assert.equal(x.body.innerHTML,'');}
for(const extra of [{maximum_close_drawdown:'-1/20'},{maximum_close_drawdown:'101/100'},{total_return:'-101/100'},{total_return:'1/0'},{start_date:'2026-02-30'},{through_date:'2026-01-01'},{return_scope:'TOTAL_RETURN'},{total_return_certified:true}]){x=setup();x.open();x.reply({...good,...extra});await tick();assert.equal(x.body.innerHTML,'');assert.match(x.body.textContent,/无效|不一致/);}
for(const d of [{...good,status:'INCOMPLETE'},{...good,recorded_fill_count:0},{...good,elapsed_calendar_days:0}]){x=setup();x.open();x.reply(d);await tick();assert.doesNotMatch(x.body.innerHTML,/10.00%/);assert.match(x.body.textContent,/不完整|尚未形成/);}
x=setup();x.open();x.c.destroy();x.reply(good);await tick();assert.doesNotMatch(x.body.innerHTML,/10.00%/);
x=setup();x.open();x.close();x.reply(good);await tick();assert.doesNotMatch(x.body.innerHTML,/10.00%/);
console.log('PASS performance: lazy GET, account/revision/genesis/plan binding, incomplete/zero no returns, late response discarded');
})().catch(e=>{console.error(e);process.exitCode=1;});
