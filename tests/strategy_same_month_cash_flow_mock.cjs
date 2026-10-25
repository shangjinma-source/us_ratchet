// Same-month cash submission: real frontend controller, synthetic HTTP transport.
const assert = require('node:assert/strict');
const {createController} = require('../web/strategy_monthly_target.js');
const response = value => ({ok:true,json:async()=>value});

(async()=>{
  const calls=[];
  const prior={status:'SAVED_TARGET',configuration_reason:'EXPLICIT_RECONFIGURE',
    target_id:'old-target',target_month:'2026-11',targets:[{security_id:'B',ticker:'BBB',quantity:1}]};
  const next={...prior,target_id:'new-target',targets:[
    {security_id:'A',ticker:'AAA',quantity:1},{security_id:'B',ticker:'BBB',quantity:1}]};
  const account={revision:'before-cash',cash_confirmation_valid:true,
    holdings:[{security_id:'B',ticker:'BBB',quantity:1}],orders:[]};
  let finishCash,finishGenerate;
  const controller=createController({storage:null,makeId:()=> 'same-month-event',
    saveCash:input=>{calls.push({step:'cash',input});return new Promise(resolve=>finishCash=resolve);},
    fetchImpl:async(url,init={})=>{
      const body=init.body?JSON.parse(init.body):null;
      calls.push({step:url,body});
      if(url.endsWith('/generate'))return new Promise(resolve=>finishGenerate=resolve);
      if(url.endsWith('/preview'))return response({status:'READY',target_id:'new-target',
        account_revision:'after-cash',reference_valid_until:null,difference:{new_orders:[]}});
      assert.equal(url,'/api/strategy-account/target');return response(prior);
    }});
  try{
    controller.setAccount(account);await controller.load();calls.length=0;
    const work=controller.configureCash({amount:'60',cash_basis:'TOTAL_UNINVESTED'});
    assert.deepEqual(calls.map(x=>x.step),['cash']);
    assert.equal(calls[0].input.cash_basis,'AVAILABLE_AFTER_RESERVATIONS');
    finishCash({...account,revision:'after-cash',cash:'60'});
    await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(calls.map(x=>x.step),['cash','/api/strategy-account/target','/api/strategy-account/target/generate']);
    assert.deepEqual(calls[2].body,{event_id:'same-month-event',reason:'EXPLICIT_RECONFIGURE',
      expected_revision:'after-cash',previous_target_id:'old-target'});
    finishGenerate(response(next));await work;
    assert.deepEqual(calls.map(x=>x.step),['cash','/api/strategy-account/target',
      '/api/strategy-account/target/generate','/api/strategy-account/target/preview']);
    assert.deepEqual(calls[3].body,{target_id:'new-target',expected_revision:'after-cash'});
    assert.equal(controller.getState().target.target_id,'new-target');
    assert.equal(controller.getState().fresh,true);
    assert.equal(calls.filter(x=>x.step==='cash').length,1);
    console.log('PASS same-month configureCash: save first, EXPLICIT_RECONFIGURE, new revision, prior target, preview after generation');
  }finally{controller.dispose();}
})().catch(error=>{console.error(error);process.exitCode=1;});
