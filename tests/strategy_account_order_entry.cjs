const assert=require('node:assert/strict'),path=require('node:path');
const api=require(path.resolve(process.argv[2]||'web/strategy_account.js'));
class Container {
 constructor(){this.forms=[];this.details=[];}
 set innerHTML(h){this.html=h;this.forms=[];this.details=[...h.matchAll(/<details data-account-disclosure="([^"]+)"/g)].map(m=>({dataset:{accountDisclosure:m[1]},open:false}));for(const m of h.matchAll(/<form data-form="([^"]+)"[^>]*>([\s\S]*?)<\/form>/g)){const fields={};for(const x of m[2].matchAll(/<(input|select)\b([^>]*)>/g)){const n=/name="([^"]+)"/.exec(x[2])?.[1];if(n)fields[n]={value:/value="([^"]*)"/.exec(x[2])?.[1]||(x[1]==='select'?'BUY':'')};}this.forms.push({dataset:{form:m[1]},fields,elements:{namedItem:n=>fields[n]}});}}
 querySelectorAll(s){return s.startsWith('details')?this.details:this.forms;}
 querySelector(s){return s.startsWith('details')?this.details.find(x=>s.includes('"'+x.dataset.accountDisclosure+'"')):this.forms.find(x=>s.includes('"'+x.dataset.form+'"'));}
 addEventListener(){}
}
global.FormData=class{constructor(f){return Object.entries(f.fields).map(([k,v])=>[k,v.value]);}};
const state=()=>({revision:'r1',holdings_revision:0,cash:'1000',cash_basis:'AVAILABLE_AFTER_RESERVATIONS',total_uninvested_cash:'1000',available_cash:'1000',reserved_cash:'0',cash_confirmation_valid:true,holdings:[{ticker:'AAA',quantity:5}],orders:[]});
(async()=>{
 let account=state(),writes=0,uncertain=false;
 const fetchImpl=async(url,init)=>{if(init.method){writes++;const b=JSON.parse(init.body);assert.equal(b.event.kind,'ORDER_OPEN');assert.equal(b.event.fee_per_share,'0');if(account.orders.some(x=>x.order_id===b.event.order_id))return {ok:false,json:async()=>({reason:'ORDER_ALREADY_EXISTS'})};account={...account,revision:'r'+(writes+1),cash_confirmation_valid:false,orders:[{...b.event,remaining_quantity:b.event.quantity}]};if(uncertain)throw Error('lost response');}return {ok:true,json:async()=>({status:'READY',account})};};
 const c=new Container(),ui=api.mount({container:c,fetchImpl,initialValuation:false,automaticValuationEnabled:false,makeId:()=> 'event-'+writes});await ui.ready;
 assert.match(c.html,/仅记账，不向券商下单/);const form=k=>c.forms.find(f=>f.dataset.form===k),details=()=>c.details.find(d=>d.dataset.accountDisclosure==='broker-order');
 details().open=true;form('order').fields.order_id.value='broker1';form('order').fields.ticker.value='AAA';form('order').fields.side.value='SELL';form('order').fields.quantity.value='2';form('order').fields.limit_price.value='120';form('fill').fields.quantity.value='1';form('fill').fields.price.value='100';ui.setRecommendedTickers(['BBB']);assert.equal(details().open,true);assert.equal(form('order').fields.side.value,'SELL');assert.equal(form('order').fields.ticker.value,'AAA');assert.equal(form('order').fields.order_id.value,'broker1');
 await ui.recordOrder({order_id:'broker1',ticker:'AAA',side:'SELL',quantity:'2',limit_price:'120'});assert.equal(form('order').fields.order_id.value,'');assert.equal(form('fill').fields.quantity.value,'1');assert.equal(form('fill').fields.price.value,'100');assert.equal(details().open,true);assert.match(ui.getState().message,/无需手动加回/);
 form('order').fields.order_id.value='broker2';ui.setRecommendedTickers(['CCC']);assert.equal(form('order').fields.order_id.value,'broker2');
 uncertain=true;await assert.rejects(ui.recordOrder({order_id:'broker2',ticker:'AAA',side:'SELL',quantity:'1',limit_price:'121'}),e=>e.code==='RECONCILE_REQUIRED');const count=writes;assert.throws(()=>ui.recordOrder({order_id:'broker2',ticker:'AAA',side:'SELL',quantity:'1',limit_price:'121'}));assert.equal(writes,count);await ui.load();assert.equal(writes,count);assert.ok(ui.getState().account.orders.some(o=>o.order_id==='broker2'));uncertain=false;
 await assert.rejects(ui.recordOrder({order_id:'broker2',ticker:'AAA',side:'SELL',quantity:'1',limit_price:'121'}));assert.match(ui.getState().message,/编号已记录/);
 console.log('order disclosure/drafts, uncertain-write readback and duplicate-id PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
