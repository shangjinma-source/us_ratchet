import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
// Explicit synthetic transport and minimal DOM; no real account, network or layout certification.
const testsDirectory = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testsDirectory, '..', 'web', 'index.html'), 'utf8');
const span=(a,b)=>{
  assert.equal(source.split(a).length,2,`Unique start marker: ${a}`);
  const rest=source.split(a)[1];
  assert(rest.includes(b),`Required end marker: ${b}`);
  return a+rest.split(b)[0];
};
const functions=[span('async function requestPlannerState(', 'function plannerInputChanged('),
 span('function invalidateParallelDeployment(', 'function renderPlannerCashBasis('),
 span('async function loadParallelDeployment(', 'function executionActionBadge(')].join('\n');
const context=vm.createContext({assert});
vm.runInContext(`
let stateData={broker_account:{account_fingerprint:'SAME'}},stateRequestSequence=0,apiGet;
const nodes={plannerCash:{value:'20000'},plannerBrokerConfirmed:{checked:true},scheduledDeploymentBody:{innerHTML:''}};
const $=id=>nodes[id],esc=x=>String(x),fmt0=x=>String(x),fmt=x=>String(x),pct=x=>String(x),renderBuyPlan=()=>{};
${functions}
`,context);
const result = await vm.runInContext(`(async()=>{
const fresh=()=>({broker_account:{account_fingerprint:'SAME'}});
const plan=id=>({status:'READY_FOR_USER_REVIEW',plan_id:id,lines:[]});
let tests=0,requests=0;
let resolveState;
apiGet=url=>{requests++;return new Promise(resolve=>resolveState=resolve);};
const stateRequest=requestPlannerState();
const firstCount=requests;
await loadParallelDeployment();
assert.equal(requests,firstCount);
assert(nodes.scheduledDeploymentBody.innerHTML.includes('正在刷新'));
assert(requestPlannerState.pendingSequence);
resolveState(fresh());await stateRequest;
assert.equal(requestPlannerState.pendingSequence,0);
apiGet=async()=>{requests++;return plan('AFTER_SUCCESS');};
await loadParallelDeployment();
assert(nodes.scheduledDeploymentBody.innerHTML.includes('AFTER_SUCCESS'));
tests++;

apiGet=async()=>{throw Error('LATEST_STATE_FAIL');};
await assert.rejects(requestPlannerState(),/LATEST_STATE_FAIL/);
assert.equal(requestPlannerState.pendingSequence,0);
const failedCount=requests;
apiGet=async()=>{requests++;return plan('FORBIDDEN_AFTER_FAIL');};
await loadParallelDeployment();
assert.equal(requests,failedCount);
assert(nodes.scheduledDeploymentBody.innerHTML.includes('刷新失败'));
assert(!nodes.scheduledDeploymentBody.innerHTML.includes('FORBIDDEN_AFTER_FAIL'));
apiGet=async()=>fresh();await requestPlannerState();
assert(!stateData.planner_refresh_error);
apiGet=async()=>plan('RECOVERY_SUCCESS');await loadParallelDeployment();
assert(nodes.scheduledDeploymentBody.innerHTML.includes('RECOVERY_SUCCESS'));
tests++;

let resolveOld,resolveNew,call=0;
apiGet=()=>new Promise(resolve=>++call===1?resolveOld=resolve:resolveNew=resolve);
const oldRequest=requestPlannerState();
const newerRequest=requestPlannerState();const newerSequence=stateRequestSequence;
resolveOld(fresh());await oldRequest;
assert.equal(requestPlannerState.pendingSequence,newerSequence);
apiGet=async()=>{requests++;return plan('FORBIDDEN_WHILE_NEW_PENDING');};
const whilePendingCount=requests;await loadParallelDeployment();assert.equal(requests,whilePendingCount);
resolveNew(fresh());await newerRequest;
assert.equal(requestPlannerState.pendingSequence,0);
tests++;

let rejectOld,resolveLatest;call=0;
apiGet=()=>new Promise((resolve,reject)=>++call===1?rejectOld=reject:resolveLatest=resolve);
const oldFailure=requestPlannerState();const latestSuccess=requestPlannerState();
resolveLatest(fresh());await latestSuccess;
apiGet=async()=>plan('LATEST_SUCCESS_VISIBLE');await loadParallelDeployment();
const html=nodes.scheduledDeploymentBody.innerHTML;
rejectOld(Error('LATE_OLD_STATE_ERROR'));await oldFailure;
assert(!stateData.planner_refresh_error);
assert.equal(requestPlannerState.pendingSequence,0);
assert.equal(nodes.scheduledDeploymentBody.innerHTML,html);
tests++;

let rejectOlder,rejectNewer;call=0;
apiGet=()=>new Promise((resolve,reject)=>++call===1?rejectOlder=reject:rejectNewer=reject);
const olderFail=requestPlannerState();const newerFail=requestPlannerState();
rejectOlder(Error('OLDER_FAILURE'));await olderFail;
assert.equal(requestPlannerState.pendingSequence,stateRequestSequence);
rejectNewer(Error('LATEST_FAILURE'));await assert.rejects(newerFail,/LATEST_FAILURE/);
assert.equal(stateData.planner_refresh_error,'LATEST_FAILURE');
assert.equal(requestPlannerState.pendingSequence,0);
apiGet=async()=>{requests++;return plan('BLOCKED_UNTIL_SUCCESS');};
const finalCount=requests;await loadParallelDeployment();assert.equal(requests,finalCount);
tests++;

let rejectStale,rejectCurrent;call=0;
apiGet=()=>new Promise((resolve,reject)=>++call===1?rejectStale=reject:rejectCurrent=reject);
const staleFailure=requestPlannerState();const currentFailure=requestPlannerState();
rejectCurrent(Error('CURRENT_FAIL_FIRST'));await assert.rejects(currentFailure,/CURRENT_FAIL_FIRST/);
rejectStale(Error('STALE_FAIL_LATER'));await staleFailure;
assert.equal(stateData.planner_refresh_error,'CURRENT_FAIL_FIRST');
assert.equal(requestPlannerState.pendingSequence,0);
tests++;

let resolveCore;apiGet=()=>new Promise(resolve=>resolveCore=resolve);
// Simulate refresh-error appearing before an already pending core response.
stateData=fresh();const core=loadParallelDeployment();
stateData.planner_refresh_error='NEW_FAILURE';
resolveCore(plan('CORE_RESULT_AFTER_ERROR'));await core;
assert(!nodes.scheduledDeploymentBody.innerHTML.includes('CORE_RESULT_AFTER_ERROR'));
tests++;
return tests;
})()`,context);
assert.equal(result,7);
process.stdout.write(JSON.stringify({status:'LATEST_STATE_PENDING_FAILURE_RUNTIME_PASS',tests:result,
 pending_core_no_request:true,latest_failure_blocks_until_success:true,
 older_finally_cannot_clear_newer_pending:true,old_errors_cannot_replace_latest_success:true,
 real_browser_layout_verified:false})+'\n');
