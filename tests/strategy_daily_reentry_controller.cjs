'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const candidate=require('../web/strategy_daily_controller_reentry_v1.js');
// Run the unchanged cash/quote/expiry suite against the versioned controller.
const filename=path.join(__dirname,'strategy_daily_controller_mock.cjs');
const original=fs.readFileSync(filename,'utf8');
const from="require('../web/strategy_daily_controller.js')";
assert.equal(original.split(from).length,2);
const suite=new Module(filename,module);suite.filename=filename;
suite.paths=Module._nodeModulePaths(__dirname);
suite._compile(original.replace(from,"require('../web/strategy_daily_controller_reentry_v1.js')"),filename);
const now=Date.parse('2026-10-28T15:00:00Z');
const model={account:{revision:'r',holdings:[{security_id:'A',quantity:0}]},
 target:{target_id:'t',proposal_id:'a'.repeat(64),proposal_targets:[{security_id:'A',ticker:'A',quantity:4}]},
 daily:{status:'WAIT',detail_status:'WAIT_REFERENCE_OR_CASH',account_revision:'r',target_id:'t',proposal_id:'a'.repeat(64),
 policy_id:'SAVED_FRONTIER_CAP50_EXIT20_REENTRY_V1',risk_monthly_targets:{A:4},effective_target_quantities:{A:0},
 daily_gate:{rows:[{security_id:'A',held:0,effective_target:0,action:'WAIT',reason:'WAIT_REENTRY_RECOVERY'}]},
 new_orders:[],reference_quotes:{}},busy:false,error:null};
let result=candidate.presentation(model,now);
assert.equal(result.rows[0].monthly_target,4);
assert.equal(result.rows[0].action,'WAIT');
assert.match(candidate.actionExplanation(result.rows[0],result,model),/等待收盘价恢复/);
model.daily.daily_gate.rows[0].reason='WAIT_REENTRY_EVIDENCE';
result=candidate.presentation(model,now);
assert.match(candidate.actionExplanation(result.rows[0],result,model),/历史数据尚未核验/);
assert.equal(result.rows[0].orders.length,0);
console.log('reentry policy and waiting explanations PASS');
