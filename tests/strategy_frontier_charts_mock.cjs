const assert=require('node:assert/strict');
const {mount}=require('../web/strategy_monthly_target_charts.js');
(async()=>{
 for(const latest of [false,true]){
  let loader,selection,reply;
  const target={target_id:'t',proposal_id:'a'.repeat(64),targets:[{security_id:'B',ticker:'B',quantity:99}]};
  const c=mount({container:{replaceChildren(){},textContent:''},latestDisplayEnabled:latest,
   createCharts:(node,load)=>{loader=load;return{destroy(){},setSelection(value){selection=value;}};},
   fetchImpl:async url=>{
    assert(url.includes(latest?'/latest-bars?':'/target/bars?'));
    const query=new URLSearchParams(url.split('?')[1]);assert.equal(query.get('expected_proposal_id'),target.proposal_id);assert.equal(query.get('security_id'),'B');
    return {ok:true,json:async()=>reply};
   }});
  c.setAccount({revision:'r',holdings:[]});c.setTarget(target);
  reply={status:latest?'DISPLAY_ONLY':'AVAILABLE',target_id:'t',proposal_id:target.proposal_id,security_id:'B',ticker:'B',account_revision:'r',executable:false,bars:[{complete:true,close:101}]};
  assert.equal(selection.stocks[0].security_id,'B');
  assert.equal((await loader('B','day')).bars[0].close,101);
  reply.proposal_id='b'.repeat(64);
  await assert.rejects(loader('B','day'),/CHART_CHANGED/);
  c.destroy();
 }
 const fs=require('node:fs'),vm=require('node:vm');
 const page=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
 const start=page.lastIndexOf('  const chartState = window.RealStrategyDaily?.getState();'),end=page.indexOf('  startStateAutoRefresh();',start);
 let handed;
 const state={account:{revision:'r',holdings:[]},target:{target_id:'t',proposal_id:'a'.repeat(64),targets:[{security_id:'A',ticker:'A',quantity:199}],proposal_targets:[{security_id:'A',ticker:'A',quantity:99},{security_id:'B',ticker:'B',quantity:99}]},daily:null};
 vm.runInNewContext(page.slice(start,end),{structuredClone,window:{RealStrategyDaily:{getState:()=>state},StrategyDailyController:require('../web/strategy_daily_controller.js'),RealStrategyMonthlyCharts:{setTarget:value=>handed=value}}});
 assert.deepEqual(Array.from(handed.targets,row=>row.security_id),['A','B']);
 assert.equal(state.target.targets.length,1);
 console.log('PASS frontier historical/latest proposal identity and bootstrap added candidate');
})().catch(error=>{console.error(error);process.exitCode=1;});
