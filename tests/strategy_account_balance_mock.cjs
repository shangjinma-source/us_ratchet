const assert=require('node:assert/strict');
const {createController,render}=require('../web/strategy_account.js');
const base={revision:'r1',cash_confirmation_valid:false,holdings:[{security_id:'sndk',ticker:'SNDK',quantity:14}],holding_costs:[{security_id:'sndk',average_cost:'1322.21',total_cost:'18510.94'}],orders:[],fills:[]};
const response=data=>({ok:true,json:async()=>data});
(async()=>{
 let calls=[],saved,resolveValue;
 const controller=createController({makeId:()=> 'cash-event',fetchImpl:async(url,init)=>{
  calls.push({url,init});
  if(init.method){saved=JSON.parse(init.body);return response({status:'READY',account:{...base,revision:'r2',cash_confirmation_valid:true,cash:'8007.8',available_cash:'8007.8',total_uninvested_cash:'8107.8',reserved_cash:'100'}});}
  if(url.endsWith('/valuation'))return new Promise(resolve=>{resolveValue=resolve;});
  return response({status:'READY',account:base});
 }});
 await controller.load();
 assert.match(render(controller.getState()),/持仓金额（成本口径）<strong>\$18,510.94/);
 assert.match(render(controller.getState()),/可用现金<strong>请在今日建议填写/);
 const saving=controller.confirmCash({amount:'8,007.8',cash_basis:'TOTAL_UNINVESTED'});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(saved.event.amount,'8007.8');
 assert.throws(()=>controller.confirmCash({amount:'8,00.7'}));
 assert.equal(saved.event.cash_basis,'AVAILABLE_AFTER_RESERVATIONS');
 assert.equal(calls.filter(c=>c.init.method).length,1);
 const interim=render(controller.getState());
 assert.match(interim,/账户总额（成本口径）<strong>\$26,618.74/,'frozen cash included exactly once');
 assert.match(interim,/可用现金<strong>\$8,007.80/);
 assert(!interim.includes('余额口径'));assert(!interim.includes('data-form="cash"'));
 resolveValue(response({status:'BLOCKED',reason:'QUOTE_UNAVAILABLE'}));
 await saving;
 assert.match(controller.getState().message,/市值暂不可用/); // Save succeeded; optional valuation reports its own failure.
 assert.equal(controller.getState().busy,false);
 assert.equal(controller.getState().account.revision,'r2');
 assert.match(render(controller.getState()),/账户总额（成本口径）<strong>\$26,618.74/);
 let posts=0,reads=0;
 const filled=createController({makeId:()=> 'fill-event',fetchImpl:async(url,init)=>{
  if(init.method){posts++;return response({status:'READY',account:{...base,revision:'r3'}});}
  if(url.endsWith('/valuation')){reads++;throw Error('network down');}
  return response({status:'READY',account:base});
 }});
 await filled.load();await filled.recordFill({ticker:'SNDK',side:'BUY',quantity:1,price:100,executed_at:'2026-10-19T22:00'});
 assert.equal(posts,1);assert.equal(reads,1);assert.equal(filled.getState().message,'市值暂不可用，当前按成本显示。');assert.equal(filled.getState().busy,false);
 let refreshReads=[];
 const valued=createController({fetchImpl:async url=>{refreshReads.push(url);return response(url.endsWith('/valuation')?{status:'READY',account_revision:'r1',market_value:'19000',strategy_total:'27000',holdings:[],valued_at:'2026-10-19T14:00:00Z'}:{status:'READY',account:{...base,cash_confirmation_valid:true,cash:'8000',total_uninvested_cash:'8000'}});}});
 await valued.refresh();assert.equal(refreshReads.length,2);
 assert.match(render(valued.getState()),/持仓市值<strong>\$19,000.00/);assert.match(render(valued.getState()),/账户总额<strong>\$27,000.00/);
 console.log('PASS simple account balances: cost fallback, fixed available cash, reserved total, automatic valuation, saved POST survives quote failure');
})().catch(error=>{console.error(error);process.exitCode=1;});
