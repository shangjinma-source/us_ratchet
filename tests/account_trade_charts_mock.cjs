const assert=require('node:assert/strict');
const {tradeProfitText,mountTradeCharts}=require('../web/strategy_account.js');
let load,markers,selection,destroyed=0;
const element=()=>({style:{},append(){},replaceChildren(){},textContent:''});global.document={createElement:element};
global.SelectedStockCharts={createSelectedStockCharts:(el,fn)=>{load=fn;return{setFills:f=>markers=f,setSelection:s=>selection=s,destroy:()=>destroyed++};}};
(async()=>{
const row={security_id:'A',ticker:'AAA',quantity:0,buy_quantity:10,sell_quantity:10,buy_amount:'1000',sell_amount:'1100',gross_cost:'0',realized_gross:'100'};
assert(tradeProfitText(row,null).includes('已实现 +$100.00'));
assert(tradeProfitText({...row,quantity:2,gross_cost:'200'},null).includes('待更新市值'));
assert(tradeProfitText({...row,quantity:2,gross_cost:'200'},{holdings:[{security_id:'A',price:'90'}]}).includes('-$20.00'));
let reply={status:'DISPLAY_ONLY',executable:false,account_revision:'r',security_id:'A',ticker:'AAA',as_of:'2026-11-13',price:100,bars:[{date:'2026-11-13',open:100,high:100,low:100,close:100,volume:1}]};
const ui=mountTradeCharts(element(),async()=>({ok:true,json:async()=>reply}));const state={account:{revision:'r',fill_correction_revision:'c',trade_results:[row],fills:[{side:'BUY'},{side:'SELL'}]}};
ui.update(state);assert.equal(selection.trade_history,true);assert.equal(selection.stocks[0].quantity,0);assert.equal(markers.length,2);
assert.equal((await load('AAA','day')).status,'AVAILABLE');ui.update(state);assert.equal(destroyed,0);
reply={...reply,account_revision:'wrong'};await assert.rejects(load('AAA','day'),/账户已变化/);
ui.update({account:{...state.account,fill_correction_revision:'c2'}});assert.equal(destroyed,1);
console.log('PASS closed charts, markers, corrected revision, profit and missing valuation');
})().catch(e=>{console.error(e);process.exitCode=1;});
