const assert=require('node:assert/strict');
const {createController}=require('../web/strategy_roa_controller.js');
const cached={receivedAt:1000,advice:{strategy_epoch:'E',strategy_kind:'ROA_DEFENSIVE_V1',executable:true,rows:[{ticker:'AMAT',security_id:'A',held:0,target_quantity:10,side:'BUY',quantity:10,limit_price:'332'}]}};
const c=createController({request:async()=>{throw Error('NETWORK_LOST')},readAccount:async()=>null,eventId:()=>'',pendingStore:{read:()=>null},expectedEpoch:'E',now:()=>2000,historyStore:{read:()=>cached}});
assert.equal(c.getState().advice,null);assert.equal(c.getState().lastAdvice.rows[0].limit_price,'332');
c.load().then(()=>{assert.equal(c.getState().advice,null);assert.equal(c.getState().lastAdvice.rows[0].quantity,10);assert.equal(c.getState().error,'NETWORK_LOST');console.log('PASS cached reference never becomes executable after reload or failure');});
