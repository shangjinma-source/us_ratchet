'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/index.html','utf8');
const begin=source.indexOf('const automaticSnapshotValuationEnabled =');
const code=source.slice(begin,source.indexOf('function renderRealStrategyAccountState',begin));
assert(code.includes('automaticSnapshotValuationEnabled = true'),'enabled after live V9 validation');
for(const enabled of [false,true]){let requests=0;const context={realStrategyInitializing:true,window:{RealStrategyAccount:{getState:()=>({loaded:true,busy:false,account:{revision:'r'}}),valuation:quiet=>{assert.equal(quiet,true);requests++;return new Promise(()=>{});}}}};vm.createContext(context);vm.runInContext(code.replace('Enabled = true','Enabled = '+enabled),context);context.requestBackgroundStrategyValuation();assert.equal(requests,0);context.realStrategyInitializing=false;assert.equal(context.requestBackgroundStrategyValuation(),undefined,'does not await unresolved network');assert.equal(requests,enabled?1:0);}
console.log('PASS background valuation enabled after validation, waits for initialization, never awaits network');
