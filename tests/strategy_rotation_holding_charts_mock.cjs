const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_monthly_target_charts.js');
(async()=>{
 let selection,load,request;
 const c=mount({container:{replaceChildren(){},textContent:''},createCharts:(node,loader)=>{load=loader;return {destroy(){},setSelection(value){selection=value;},setFills(){}};},fetchImpl:async url=>{request=url;return {ok:true,json:async()=>({scope:'RECORDED_HOLDING_HISTORY',account_revision:'r1',security_id:'OLD',ticker:'OLD'})};}});
 c.setAccount({revision:'r1',holdings:[{security_id:'OLD',ticker:'OLD',quantity:14}]});
 c.setTarget({target_id:'new',targets:[{security_id:'NEW',ticker:'NEW',quantity:5}]});
 assert.deepEqual(selection.stocks.map(x=>x.ticker),['NEW','OLD']);
 assert.equal(selection.stocks[1].recorded_holding,true);
 await load('OLD','day');assert(request.startsWith('/api/strategy-account/holding-bars?'));
 c.setTarget({target_id:'cash',targets:[]});assert.equal(selection.stocks[0].ticker,'OLD');
 c.setAccount({revision:'r2',holdings:[{security_id:'OLD',ticker:'OLD',quantity:6}]});assert.equal(selection.stocks[0].quantity,6);
 c.setTarget({target_id:'same',targets:[{security_id:'OLD',ticker:'OLD',quantity:4}]});assert.equal(selection.stocks.length,1);assert.equal(selection.stocks[0].quantity,4);assert.equal(selection.stocks[0].recorded_holding,false);
 c.setTarget({target_id:'new',targets:[{security_id:'NEW',ticker:'NEW',quantity:5}]});
 c.setAccount({revision:'r3',holdings:[]});assert.deepEqual(selection.stocks.map(x=>x.ticker),['NEW']);
 c.destroy();console.log('PASS rotation retains unsold holdings, cash target, partial sale, no duplicate, cleared holding removed');
})().catch(e=>{console.error(e);process.exitCode=1;});
