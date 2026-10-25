import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
// Explicit synthetic transport and minimal DOM; no real account, network or layout certification.
const testsDirectory = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testsDirectory, '..', 'web', 'index.html'), 'utf8');
function span(start, end) {
  assert.equal(source.split(start).length, 2);
  const rest=source.split(start)[1];
  assert(rest.includes(end),`Required end marker: ${end}`);
  return start + rest.split(end)[0];
}
const functions = [
  span('function executionConstraints(', 'function admissionCell('),
  span('function plannerGapModel(', 'async function loadParallelDeployment('),
  span('async function loadParallelDeployment(', 'function executionActionBadge('),
  span('async function requestPlannerState(', 'async function refreshBuyPlan('),
  span('async function refreshBuyPlan(', 'function plannerRowNote('),
  span('function plannerRowNote(', 'function currentMarketDate('),
].join('\n');
const context = vm.createContext({assert, JSON, console});
vm.runInContext(`
const PLANNER_LOT_SIZE=1, PLANNER_COMPACT_TARGET=4, PLANNER_EXECUTION_VENUE='test';
const PLANNER_RECENT_KEY='recent',PLANNER_CASH_KEY='cash';
const fmt0=x=>String(x),fmt=x=>String(x),pct=x=>String(x),esc=x=>String(x);
let stateData=null,currentPlannerSnapshot=null,stateRequestSequence=0,apiGet;
const nodes={buyPlanBody:{innerHTML:''},scheduledDeploymentBody:{innerHTML:''},
 plannerCash:{value:'20000'},plannerBrokerConfirmed:{checked:true},btnRefreshBuyPlan:{}};
const $=id=>nodes[id],currentMarketDate=()=> '2026-10-09';
const storage=new Map(),localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)};
const renderExecutiveBrief=()=>{},renderExecution=()=>{};
const data={initialized:true,as_of:'2026-10-09',
 broker_account:{available:true,deployable_cash_usd:10615.9,account_fingerprint:'SAME'},
 account_readiness:{reserve_book_cash:3700,position_gaps:{account_fingerprint:'SAME',rows:[
  {ticker:'AAA',gap_amount:800,gap_ratio:.8,gap_rank:1,position_kind:'real_position'}]}},
 execution:{items:[{ticker:'AAA',side:'BUY',source:'tactical_limit',action:'BUY_NOW',
  amount:50,limit:100,live_price:99}]},
 execution_constraints:{lot_size:1,allow_fractional:false,fee_bps:10,min_fee:2,buy_plan_compact_target:4},
 symbols:[{ticker:'AAA',tactical:{action:'BUY_NOW',amount:50,limit:100,execution_context:{budget_basis:{
   source:'strategy_state_reserve_cash',reserve_cash_usd:250,reserve_ratio:.2,raw_budget_usd:50,current_cash_not_consumed:true}}}}]};
${functions}
`, context);
const result = await vm.runInContext(`(async()=>{
let tests=0;
const plan=id=>({status:'READY_FOR_USER_REVIEW',plan_id:id,cash_deployed:100,cash_remaining:19900,lines:[]});
stateData=data;
renderBuyPlan(data);
assert.equal(nodes.plannerCash.value,'20000');
assert(nodes.buyPlanBody.innerHTML.includes('输入现金（USD） $20000'));
assert(nodes.buyPlanBody.innerHTML.includes('券商已声明 $10615.9'));
assert(nodes.buyPlanBody.innerHTML.includes('策略账本储备（非券商现金） $3700'));
assert(nodes.buyPlanBody.innerHTML.includes('本通道未分配 $20000'));
assert(nodes.buyPlanBody.innerHTML.includes('旧储备 $250 × 0.2'));
assert.equal(currentPlannerSnapshot,null);
assert.equal(data.execution.items[0].amount,50);
assert.equal(data.symbols[0].tactical.amount,50);
assert.equal(data.symbols[0].tactical.execution_context.budget_basis.raw_budget_usd,50);
assert(plannerSignalDiagnostics(data,20000)[0].reasons.some(x=>x.includes('策略预算')));
tests++;

data.execution.items[0].amount=500;
renderBuyPlan(data);
assert.equal(currentPlannerSnapshot.rows[0].shares,5);
assert.equal(currentPlannerSnapshot.rows[0].notional,500);
assert.equal(currentPlannerSnapshot.rows[0].amount,502);
assert(nodes.buyPlanBody.innerHTML.includes('战术整股草案含费占用 $502'));
assert(nodes.buyPlanBody.innerHTML.includes('本通道未分配 $19498'));
tests++;

let resolveA;const requests=[];
apiGet=url=>{requests.push(url);return new Promise(resolve=>resolveA=resolve);};
const pendingA=loadParallelDeployment();
nodes.plannerCash.value='10000';plannerInputChanged();
assert(nodes.scheduledDeploymentBody.innerHTML.includes('旧草案已失效'));
apiGet=async url=>{requests.push(url);return plan('NEW_B');};
await loadParallelDeployment();const htmlB=nodes.scheduledDeploymentBody.innerHTML;
assert(htmlB.includes('NEW_B'));
resolveA(plan('OLD_A'));await pendingA;
assert.equal(nodes.scheduledDeploymentBody.innerHTML,htmlB);
assert(requests[0].includes('cash_usd=20000'));
assert(requests[1].includes('cash_usd=10000'));
tests++;

let resolveOld;apiGet=()=>new Promise(resolve=>resolveOld=resolve);
const oldStatePlan=loadParallelDeployment();
apiGet=async()=>({...data,execution:{items:[]}});
await refreshBuyPlan();
assert.equal(nodes.plannerCash.value,'10000');
assert.equal(stateData.broker_account.account_fingerprint,'SAME');
resolveOld(plan('STALE_SAME_CASH_AND_FINGERPRINT'));await oldStatePlan;
assert(!nodes.scheduledDeploymentBody.innerHTML.includes('STALE_SAME_CASH_AND_FINGERPRINT'));
assert(nodes.scheduledDeploymentBody.innerHTML.includes('重新生成核心草案'));
tests++;

let resolveConfirm;apiGet=()=>new Promise(resolve=>resolveConfirm=resolve);
const confirmPlan=loadParallelDeployment();
nodes.plannerBrokerConfirmed.checked=false;
invalidateParallelDeployment('持仓确认已变化');
resolveConfirm(plan('STALE_CONFIRM'));await confirmPlan;
assert(!nodes.scheduledDeploymentBody.innerHTML.includes('STALE_CONFIRM'));
tests++;

nodes.plannerBrokerConfirmed.checked=true;
apiGet=async()=>plan('VISIBLE_BEFORE_FAILURE');await loadParallelDeployment();
assert(nodes.scheduledDeploymentBody.innerHTML.includes('VISIBLE_BEFORE_FAILURE'));
apiGet=async()=>{throw Error('STATE_OFFLINE');};await refreshBuyPlan();
assert(!nodes.scheduledDeploymentBody.innerHTML.includes('VISIBLE_BEFORE_FAILURE'));
assert(nodes.buyPlanBody.innerHTML.includes('策略刷新失败'));
tests++;
apiGet=async()=>data;await requestPlannerState(); // Explicit recovery before further core tests.

let rejectOld;apiGet=()=>new Promise((resolve,reject)=>rejectOld=reject);
const oldFailure=loadParallelDeployment();
nodes.plannerCash.value='15000';plannerInputChanged();
apiGet=async()=>plan('NEW_AFTER_OLD_PENDING');await loadParallelDeployment();
const latest=nodes.scheduledDeploymentBody.innerHTML;
rejectOld(Error('LATE_OLD_ERROR'));await oldFailure;
assert.equal(nodes.scheduledDeploymentBody.innerHTML,latest);
tests++;

let resolveFingerprint;apiGet=()=>new Promise(resolve=>resolveFingerprint=resolve);
const fingerprintPlan=loadParallelDeployment();
stateData={...data,broker_account:{...data.broker_account,account_fingerprint:'CHANGED'}};
resolveFingerprint(plan('STALE_FINGERPRINT'));await fingerprintPlan;
assert(!nodes.scheduledDeploymentBody.innerHTML.includes('STALE_FINGERPRINT'));
tests++;

return {status:'CURRENT_HTML_FUNCTION_RUNTIME_PASS',tests,
 cash_not_written_to_account:true,api_requests_mocked:true,browser_layout_verified:false};
})()`, context);
assert.equal(result.tests,8);
process.stdout.write(JSON.stringify({status:'CURRENT_HTML_FUNCTION_RUNTIME_PASS',tests:result.tests,
  stale_cash_state_confirmation_fingerprint_and_errors_rejected:true,
  cash_20000_does_not_expand_original_50_budget:true,real_dom_layout_verified:false})+'\n');
