const assert=require('node:assert/strict'),path=require('node:path');
const api=require(path.resolve(process.argv[2]||'web/strategy_account.js'));
const a=()=>({revision:'r1',cash:'1000',cash_confirmation_valid:true,holdings:[],orders:[]});
const storage=()=>{const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};
(async()=>{
 for(const durable of [false,true]){
  const store=api.browserPendingFillStore(storage(),'isolated'),account=a();let state=account,first=true,writes=[];
  const fetchImpl=async(url,init)=>{if(init.method){const body=JSON.parse(init.body);writes.push(body);if(first){first=false;if(durable)state={...account,revision:'r2',orders:[{order_id:'b1',ticker:'AAA',side:'BUY',quantity:2,remaining_quantity:2,limit_price:'100',reserved_cash:'200'}]};throw Error('unknown');}state={...account,revision:'r2',orders:[{order_id:'b1',ticker:'AAA',side:'BUY',quantity:2,remaining_quantity:2,limit_price:'100',reserved_cash:'200'}]};}return {ok:true,json:async()=>({status:'READY',account:state})};};
  const options={fetchImpl,pendingFillStore:store,automaticValuationEnabled:false,makeId:()=> 'stable-event'};
  let ui=api.createController(options);await ui.load();await assert.rejects(ui.recordOrder({order_id:'b1',ticker:'AAA',side:'BUY',quantity:2,limit_price:'100'}));assert.ok(store.read());ui.dispose();
  ui=api.createController(options);await ui.load();assert.equal(writes.length,1);
  if(durable){assert.equal(store.read(),null);assert.match(ui.getState().message,/已经保存/);}
  else {assert.equal(ui.getState().pendingFill,true);await ui.recoverFill();assert.equal(writes.length,2);assert.deepEqual(writes[1],writes[0]);assert.equal(store.read(),null);}
 }
 // Same broker id with different contents is not an exact success acknowledgement.
 const store=api.browserPendingFillStore(storage(),'conflict');store.write({eventId:'e',key:JSON.stringify({path:'/events',expected:'r1',fields:{kind:'ORDER_OPEN',order_id:'b',ticker:'AAA',side:'BUY',quantity:2,limit_price:'100',fee_per_share:'0'}})});
 const ui=api.createController({pendingFillStore:store,automaticValuationEnabled:false,fetchImpl:async()=>({ok:true,json:async()=>({status:'READY',account:{...a(),revision:'r2',orders:[{order_id:'b',ticker:'BBB',side:'BUY',quantity:2,remaining_quantity:2,limit_price:'100',reserved_cash:'200'}]}})})});await ui.load();assert.doesNotMatch(ui.getState().message,/已经保存/);assert.equal(store.read(),null);
 // CANCEL absence alone on unchanged revision remains uncertain, never auto-posted.
 store.write({eventId:'cancel',key:JSON.stringify({path:'/events',expected:'r2',fields:{kind:'CANCEL',order_id:'b'}})});let count=0;
 const c=api.createController({pendingFillStore:store,automaticValuationEnabled:false,fetchImpl:async()=>{count++;return {ok:true,json:async()=>({status:'READY',account:{...a(),revision:'r2'}})}}});await c.load();assert.equal(c.getState().pendingFill,true);assert.equal(count,1);assert.ok(store.read());
 // A confirmed 4xx rejection did not write: retain draft ability, release persisted intent.
 const rejectedStore=api.browserPendingFillStore(storage(),'rejected');let posted=[];
 const rejected=api.createController({pendingFillStore:rejectedStore,automaticValuationEnabled:false,makeId:()=> 'r-'+posted.length,fetchImpl:async(url,init)=>{if(init.method){const b=JSON.parse(init.body);posted.push(b);if(posted.length===1)return {ok:false,status:400,json:async()=>({status:'BLOCKED',reason:'ORDER_ALREADY_EXISTS'})};return {ok:true,json:async()=>({status:'READY',account:{...a(),revision:'r2'}})};}return {ok:true,json:async()=>({status:'READY',account:a()})};}});
 await rejected.load();await assert.rejects(rejected.recordOrder({order_id:'wrong',ticker:'AAA',side:'BUY',quantity:2,limit_price:'100'}));assert.equal(rejectedStore.read(),null);await rejected.load();assert.equal(rejected.getState().pendingFill,false);await rejected.recordOrder({order_id:'correct',ticker:'AAA',side:'BUY',quantity:2,limit_price:'100'});assert.equal(posted.length,2);assert.notEqual(posted[0].event.event_id,posted[1].event.event_id);
 console.log('persistent order/cancel unknown outcome, exact matching and same event replay PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
