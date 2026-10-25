const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_monthly_target_charts.js');
(async()=>{
 let loader,selection,resolve,requests=0,destroyed=0;
 const container={replaceChildren(){},textContent:''};
 const c=mount({container,createCharts:(node,load)=>{loader=load;return{destroy(){destroyed++;},setSelection(s){selection=s;},setFills(){}};},fetchImpl:async url=>{requests++;assert(url.startsWith('/api/strategy-account/holding-bars?'));assert(!url.includes('target_id'));return new Promise(r=>resolve=r);}});
 const account={revision:'a',holdings:[{security_id:'S',ticker:'SNDK',quantity:14}],fills:[]};
 c.setAccount(account);assert(selection.recorded_holding);assert.equal(selection.stocks[0].quantity,14);assert.equal(requests,0);
 c.setAccount(account);assert.equal(destroyed,0);
 const old=loader('SNDK','day');c.setAccount({...account,revision:'b'});resolve({ok:true,json:async()=>({scope:'RECORDED_HOLDING_HISTORY',account_revision:'a',security_id:'S',ticker:'SNDK'})});await assert.rejects(old,/HOLDING_CHART_CHANGED/);
 const wrong=loader('SNDK','day');resolve({ok:true,json:async()=>({scope:'MONTHLY_TARGET',account_revision:'b',security_id:'S',ticker:'SNDK'})});await assert.rejects(wrong,/HOLDING_CHART_CHANGED/);
 const correct=loader('SNDK','day');resolve({ok:true,json:async()=>({scope:'RECORDED_HOLDING_HISTORY',account_revision:'b',security_id:'S',ticker:'SNDK'})});await correct;
 c.setAccount(null);assert(container.textContent.includes('尚未配置'));c.destroy();
 console.log('PASS holding charts: no fake target, recorded scope, revision race, clearing account');
})().catch(e=>{console.error(e);process.exitCode=1;});
