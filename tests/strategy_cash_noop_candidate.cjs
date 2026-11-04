const assert=require('node:assert/strict');
const {createController}=require('../docs/candidates/strategy_daily_controller_cash_noop.js');
function fixture(month='2026-11'){
 let account={revision:'r1',holdings:[],available_cash:'100',cash:'100',cash_basis:'AVAILABLE_AFTER_RESERVATIONS',cash_confirmation_valid:true,execution_ready:true,holdings_revision:2,cash_confirmed_for_holdings_revision:2,cash_summary:{last_confirmation:{amount:'100',cash_basis:'AVAILABLE_AFTER_RESERVATIONS'},recorded_fill_cash_delta_since_confirmation:'0'}};
 let target={target_id:'t1',server_month:'2026-11',target_month:month,targets:[]},writes=0,generates=0,previews=0,fail=false;
 return {get writes(){return writes},get generates(){return generates},get previews(){return previews},account,fail:()=>{fail=true},loadAccount:async()=>structuredClone(account),loadTarget:async()=>structuredClone(target),saveCash:async()=>{writes++;if(fail){fail=false;throw Object.assign(Error('RECONCILE_REQUIRED'),{write_may_have_occurred:true});}account.revision='r'+(writes+1);return structuredClone(account)},generateTarget:async()=>{generates++;target={...target,target_month:'2026-11',target_id:'t2'};return structuredClone(target)},previewDaily:async b=>{previews++;return {status:'WAIT',reason:'WAIT_POLICY_REVIEW_SESSION',account_revision:b.expected_revision,target_id:b.target_id,new_orders:[]}}};
}
// The optimization must preserve the existing account amount grammar exactly.
const fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../web/strategy_account.js'),'utf8');
const original=source.match(/function amount\(value\)\{[^\n]+/)[0];
const parse=Function('issue',original+';return amount;')(code=>Error(code));
for(const value of ['100/1','1e2','0100'])assert.throws(()=>parse(value));
(async()=>{
 let checks=0;
 for(const value of ['100','100.00',' 100.0 ']){const f=fixture();await createController(f).saveBalance({amount:value});assert.equal(f.writes,0);assert.equal(f.previews,1);checks++;}
 for(const value of ['99','101','100/1','1e2','0100','100.000000000000000001']){const f=fixture();await createController(f).saveBalance({amount:value});assert.equal(f.writes,1);checks++;} // Invalid input goes to original form validator, never silently skips.
 for(const mutate of [a=>a.cash_confirmation_valid=false,a=>a.cash_confirmed_for_holdings_revision=1,a=>a.cash='90',a=>a.cash_basis='TOTAL_UNINVESTED',a=>delete a.cash_summary,a=>a.cash_summary.recorded_fill_cash_delta_since_confirmation='1',a=>a.execution_ready=false]){const f=fixture();mutate(f.account);await createController(f).saveBalance({amount:'100'});assert.equal(f.writes,1);checks++;}
 {const f=fixture('2026-10');await createController(f).saveBalance({amount:'100'});assert.equal(f.writes,0);assert.equal(f.generates,1);assert.equal(f.previews,1);checks++;}
 {const f=fixture();const c=createController(f);f.account.cash_confirmation_valid=false;f.fail();await assert.rejects(c.saveBalance({amount:'100'}),/RECONCILE_REQUIRED/);f.account.cash_confirmation_valid=true;await c.saveBalance({amount:'100'});assert.equal(f.writes,2);checks++;}
 {const f=fixture();await assert.rejects(createController(f).saveBalance({amount:'100',expected_revision:'old'}),/CASH_INPUT_SNAPSHOT_CHANGED/);assert.equal(f.writes,0);checks++;}
 {const f=fixture();f.account.available_cash='100/1';await createController(f).saveBalance({amount:'100.00'});assert.equal(f.writes,0);checks++;}
 console.log('PASS cash noop candidate '+checks+' cases');
})().catch(e=>{console.error(e);process.exitCode=1});
