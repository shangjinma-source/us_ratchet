const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const fixture=require('./fixtures/intraday_initial_retarget_controller.json');
const api=require('../web/current_research_intraday_initial_retarget_controller.js');
function box(){return{innerHTML:'',querySelectorAll(){return[];}};}
function memoryStorage(){let value=null;return{getItem:()=>value,setItem:(_,v)=>{value=v;},removeItem:()=>{value=null;}};}
function setup(moduleAPI=api,storage=memoryStorage()){
 let now=Date.parse(fixture.now),queue=[],timers=[],calls=[],accepted=[];
 const controls=box();
 const c=moduleAPI.create({controls,binding:fixture.binding,pendingStore:moduleAPI.createPendingStore(storage,'pending-test'),onAccepted:async a=>accepted.push(a),uuid:()=> 'initial-controller-test',
  clock:{now:()=>now,set:fn=>{timers.push(fn);return timers.length;},clear:()=>{}},
  fetcher:(url,options)=>{calls.push({url,options});return new Promise((resolve,reject)=>queue.push({resolve,reject}));}});
 return{c,controls,calls,accepted,storage,reply(data,ok=true){queue.shift().resolve({ok,status:ok?200:400,json:async()=>structuredClone(data)});},fail(){queue.shift().reject(Error('lost response'));},advance(){now+=121000;timers.forEach(f=>f());}};
}
async function preview(x){const p=x.c.preview();x.reply(fixture.preview);await p;}
(async()=>{
 let x=setup();assert.equal(x.calls.length,0);await preview(x);assert.match(x.controls.innerHTML,/接受此纸面调仓/);
 assert.deepEqual(Object.keys(JSON.parse(x.calls[0].options.body)).sort(),['account_id','expected_revision']);
 let p=x.c.preview();assert.doesNotMatch(x.controls.innerHTML,/接受此纸面调仓|限价 \$/);x.reply(fixture.preview);await p;
 let accept=x.c.accept();await assert.rejects(x.c.accept());x.fail();await assert.rejects(accept);const body=x.calls.at(-1).options.body;
 await assert.rejects(x.c.preview());p=x.c.retry();assert.equal(x.calls.at(-1).options.body,body);x.reply(fixture.accepted);await p;
 assert.equal(x.accepted.length,1);assert.equal(x.accepted[0].cash,fixture.binding.cash);assert.equal(x.c.pendingRequest(),null);await assert.rejects(x.c.preview());
 x=setup();await preview(x);x.advance();assert.doesNotMatch(x.controls.innerHTML,/接受此纸面调仓|限价 \$/);await assert.rejects(x.c.accept());assert.equal(x.calls.length,1);
 x=setup();p=x.c.preview();x.c.invalidate();x.reply(fixture.preview);await assert.rejects(p);assert.doesNotMatch(x.controls.innerHTML,/接受此纸面调仓/);
 x=setup();await preview(x);p=x.c.accept();x.reply({mutation_outcome:'UNKNOWN_RETRY_SAME_REQUEST'},false);await assert.rejects(p);assert.ok(x.c.pendingRequest());x.c.invalidate();assert.ok(x.c.pendingRequest());await assert.rejects(x.c.retry());assert.equal(x.accepted.length,0);
 for(const mutate of [d=>d.proposal.actual_cash='999999',d=>d.proposal.account_revision='f'.repeat(64),d=>d.proposal.orders[0].ticker='FAKE',d=>d.proposal.orders[0].limit_price='999999',d=>d.proposal.target_quantities.unknown=1]){
  x=setup();p=x.c.preview();const bad=structuredClone(fixture.preview);mutate(bad);x.reply(bad);await assert.rejects(p);assert.doesNotMatch(x.controls.innerHTML,/接受此纸面调仓/);
 }
 x=setup();await preview(x);p=x.c.accept();const bad=structuredClone(fixture.accepted);bad.account.original_acceptance_id='f'.repeat(64);x.reply(bad);await assert.rejects(p);assert.ok(x.c.pendingRequest());assert.equal(x.accepted.length,0);
 x=setup();await preview(x);p=x.c.accept();x.reply({mutation_outcome:'NOT_APPLIED'},false);await assert.rejects(p);assert.equal(x.c.pendingRequest(),null);await preview(x);
 x=setup();await preview(x);p=x.c.accept();const persistedBody=x.calls.at(-1).options.body;assert.ok(x.storage.getItem('pending-test'));x.fail();await assert.rejects(p);x.c.invalidate();
 let recovered=setup(api,x.storage);recovered.advance();assert.doesNotMatch(recovered.controls.innerHTML,/接受此纸面调仓|限价 \$/);await assert.rejects(recovered.c.preview());p=recovered.c.retry();assert.equal(recovered.calls[0].options.body,persistedBody);recovered.reply(fixture.accepted);await p;assert.equal(recovered.storage.getItem('pending-test'),null);assert.equal(recovered.accepted.length,1);
 const quota=memoryStorage();quota.setItem=()=>{throw Error('quota');};x=setup(api,quota);await preview(x);await assert.rejects(x.c.accept());assert.equal(x.calls.length,1);assert.match(x.controls.innerHTML,/未发送请求/);
 const corrupt=memoryStorage();corrupt.setItem('pending-test','{"schema":"wrong"}');assert.throws(()=>setup(api,corrupt));
 const writeThenThrow=memoryStorage(),originalSet=writeThenThrow.setItem;writeThenThrow.setItem=(key,value)=>{originalSet(key,value);throw Error('storage write uncertain');};x=setup(api,writeThenThrow);await preview(x);await assert.rejects(x.c.accept());assert.equal(x.calls.length,1);recovered=setup(api,writeThenThrow);assert.ok(recovered.c.pendingRequest());assert.doesNotMatch(recovered.controls.innerHTML,/接受此纸面调仓|限价 \$/);
 x=setup();p=x.c.preview();const noAction=structuredClone(fixture.preview);Object.assign(noAction.proposal,{orders:[],wait_cash:[],target_quantities:Object.fromEntries(fixture.binding.positions.map(p=>[p.security_id,p.quantity])),reserved_buy_cash:'0',unreserved_cash:fixture.binding.cash,action:'NO_ACTION'});noAction.status='NO_ACTION';x.reply(noAction);await p;assert.doesNotMatch(x.controls.innerHTML,/接受此纸面调仓/);await assert.rejects(x.c.accept());
 function openOptions(storage=memoryStorage()){return {accountId:fixture.binding.account_id,controls:box(),pendingStore:api.createPendingStore(storage,'pending-test'),onAccepted:async()=>{},clock:{now:()=>Date.parse(fixture.now),set:()=>1,clear:()=>{}}};}
 let opens=0,options=openOptions();options.fetcher=async(url,request)=>{opens++;assert.match(url,/\/context\?account_id=/);assert.equal(request.method,'GET');return{ok:true,json:async()=>structuredClone(fixture.context)};};let opened=await api.open(options);assert.equal(opened.kind,'INITIAL');assert.equal(opens,1);assert.match(options.controls.innerHTML,/接受此纸面调仓/);
 options=openOptions();let handed=0;options.onAccepted=async account=>{handed++;assert.equal(account.account_id,fixture.binding.account_id);};options.fetcher=async()=>({ok:true,json:async()=>structuredClone(fixture.restored_context)});opened=await api.open(options);assert.equal(opened.kind,'ACCOUNT');assert.equal(handed,1);assert.doesNotMatch(options.controls.innerHTML,/接受此纸面调仓/);
 x=setup();await preview(x);p=x.c.accept();x.fail();await assert.rejects(p);options=openOptions(x.storage);options.fetcher=()=>assert.fail('pending must recover before context');opened=await api.open(options);assert.equal(opened.kind,'INITIAL');assert.ok(opened.controller.pendingRequest());assert.doesNotMatch(options.controls.innerHTML,/接受此纸面调仓|限价 \$/);
 options=openOptions();const cancelled=new AbortController();options.signal=cancelled.signal;options.fetcher=async()=>{cancelled.abort();return{ok:true,json:async()=>structuredClone(fixture.context)};};await assert.rejects(api.open(options));assert.doesNotMatch(options.controls.innerHTML,/接受此纸面调仓/);
 options=openOptions();options.fetcher=async()=>({ok:false,json:async()=>({status:'UNAVAILABLE'})});await assert.rejects(api.open(options));assert.doesNotMatch(options.controls.innerHTML,/接受此纸面调仓/);
 const context={structuredClone,AbortController,setTimeout,clearTimeout};context.window=context;vm.createContext(context);
 for(const file of ['current_research_intraday_multiorder.js','current_research_intraday_multiorder_controller.js','current_research_intraday_initial_retarget_controller.js'])vm.runInContext(fs.readFileSync(require.resolve('../web/'+file),'utf8'),context);
 x=setup(context.ResearchIntradayInitialRetargetController);await preview(x);p=x.c.accept();x.reply(fixture.accepted);await p;assert.equal(x.accepted.length,1);
 console.log('PASS initial retarget: real service fixture, exact cash and identity, expiry/pending removal, same-ID retry, invalidation, handoff, browser globals');
})().catch(error=>{console.error(error);process.exitCode=1;});
