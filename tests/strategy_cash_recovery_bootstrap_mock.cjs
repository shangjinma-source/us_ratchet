// Execute the production index's recovery bootstrap, not a copied approximation.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../web/index.html'),'utf8');
const start=source.indexOf("  const capitalContainer = document.createElement('div');");
const end=source.indexOf('  } catch (_) {',start);
assert(start>=0&&end>start);
const bootstrap=source.slice(start,end);
class Node{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.listeners={};this.value='';this.dataset={};}
 appendChild(child){this.children.push(child);}
 replaceChildren(...children){this.children=children;}
 addEventListener(type,handler){this.listeners[type]=handler;}
 removeEventListener(type){delete this.listeners[type];}
}
async function check(kind){
 const doc={createElement:tag=>new Node(tag,doc)};
 const panel=new Node('div',doc);let locked=false,requests=0,writes=0;
 const record={event_id:'old-pending',contribution_amount:'5000',expected_revision:'a'.repeat(64),previous_target_id:'b'.repeat(64),operation:'ARRIVAL_V2'};
 const stored=kind==='corrupt'?'{broken':kind==='pending'?JSON.stringify(record):null;
 const storage={getItem:()=>{if(kind==='unavailable')throw Error('STORAGE_DENIED');return stored;},setItem:()=>{writes++;},removeItem:()=>{writes++;}};
 const window={
  StrategyDailyController:require('../web/strategy_daily_controller.js'),
  StrategyCapitalController:require('../web/strategy_capital_controller.js'),
  StrategyCapitalMount:require('../web/strategy_capital_mount.js'),
  localStorage:storage,crypto:{randomUUID:()=>{throw Error('NEW_EVENT_FORBIDDEN');}},
  fetch:async()=>{requests++;throw Error('TEMPORARY_NETWORK_FAILURE');},
  RealStrategyDaily:{elements:{cashPanel:panel},ready:Promise.resolve(),
   getState:()=>({account:{account_id:'test'}}),setCapitalBusy:value=>{locked=value;}},
  RealStrategyAccount:{load:async()=>{throw Error('UNEXPECTED_ACCOUNT_RELOAD');}}
 };
 await vm.runInNewContext('(async()=>{'+bootstrap+'})()',{window,document:doc});
 if(window.RealStrategyCapital)await window.RealStrategyCapital.ready;
 assert.equal(writes,0,'page load cannot credit, delete, or rewrite pending records');
 if(kind==='empty'){
  assert.equal(locked,false);assert.equal(panel.children[0].hidden,true);assert.equal(requests,0);
 }else{
  assert.equal(locked,true);assert.equal(panel.children[0].hidden,false);
  if(kind==='pending'){
   assert.equal(window.RealStrategyCapital.getState().pending.event_id,'old-pending');
   assert.equal(window.RealStrategyCapital.elements.form.hidden,true);
   assert.equal(window.RealStrategyCapital.elements.recover.hidden,false);
   assert.equal(requests,1,'only a status lookup is allowed');
  }else{
   assert.match(panel.children[0].textContent,/资金状态未能核对.*暂停现金更新/);assert.equal(requests,0);
  }
 }
 window.RealStrategyCapital?.dispose();
}
(async()=>{for(const kind of ['empty','corrupt','unavailable','pending'])await check(kind);
console.log('PASS production recovery bootstrap: one entry, damaged/unreadable storage blocks cash, failed lookup preserves pending without writes');
})().catch(error=>{console.error(error);process.exitCode=1;});
