const assert=require('node:assert/strict');
const {createController,render}=require('../web/strategy_monthly_target.js');
const key='ratchet.monthly-reference.v1';
const storage={data:null,getItem(){return this.data;},setItem(k,v){assert.equal(k,key);this.data=v;}};
const account={account_id:'account1',revision:'r1',cash_confirmation_valid:true,holdings:[],orders:[]};
const target={status:'SAVED_TARGET',target_id:'t1',targets:[{security_id:'S',ticker:'SNDK',quantity:14}]};
const preview={status:'READY',target_id:'t1',account_revision:'r1',reference_valid_until:'2099-01-01T00:00:00Z',private_path:'E:/private',reference_quotes:{S:{buy_limit:'1322.21',sell_limit:'1350',observed_at:'2026-10-16T15:00:00Z',reference_valid_until:'2099-01-01T00:00:00Z',evidence_path:'private'}},difference:{new_orders:[{security_id:'S',ticker:'SNDK',side:'BUY',quantity:14,limit_price:'1322.21',execution_reason:'secret/path'}]}};
let calls=[];
const make=(options={})=>createController({storage,fetchImpl:async(url,init)=>{calls.push([url,init]);return {ok:true,json:async()=>url.endsWith('preview')?preview:target};},...options});
(async()=>{
 const first=make();first.setAccount(account);await first.load();await first.refresh();assert(first.getState().fresh);assert(storage.data);assert(!storage.data.includes('private'));assert(!storage.data.includes('secret/path'));first.dispose();
 calls=[];const second=make();second.setAccount(account);assert.equal(second.getState().preview,null);await second.load();assert.equal(calls.length,1);assert(!calls[0][1].method);assert(!second.getState().fresh);assert(render(second.getState()).includes('$1,322.21'));assert(render(second.getState()).includes('$1,350'));assert(render(second.getState()).includes('旧参考'));assert(!render(second.getState()).includes('买入 14 股'));second.dispose();
 for(const changed of [{...account,revision:'r2'},{...account,account_id:'account2'}]){const c=make();c.setAccount(changed);await c.load();assert.equal(c.getState().preview,null);c.dispose();}
 const changedTarget=make({fetchImpl:async()=>({ok:true,json:async()=>({...target,target_id:'t2'})})});changedTarget.setAccount(account);await changedTarget.load();assert.equal(changedTarget.getState().preview,null);changedTarget.dispose();
 const saved=storage.data;
 for(const raw of ['{bad', 'x'.repeat(100001),JSON.stringify({version:2,account_id:'account1',preview}),JSON.stringify({version:1,account_id:'account1',preview:{...preview,difference:{new_orders:[{side:'DROP'}]}}})]){storage.data=raw;const c=make();c.setAccount(account);await c.load();assert.equal(c.getState().preview,null);c.dispose();}
 storage.data=saved;
 const reverse=make();await reverse.load();reverse.setAccount(account);assert(reverse.getState().preview);assert(!reverse.getState().fresh);reverse.dispose();
 const denied=make({storage:{getItem(){throw Error('denied');},setItem(){throw Error('quota');}}});denied.setAccount(account);await denied.load();await denied.refresh();assert(denied.getState().fresh);denied.dispose();
 const stale=JSON.parse(saved);stale.preview.reference_valid_until='2020-01-01T00:00:00Z';storage.data=JSON.stringify(stale);const old=make();old.setAccount(account);await old.load();assert(old.getState().preview);assert(!old.getState().fresh);old.dispose();
 console.log('PASS cached references: reload is read-only/stale, revision/target/account binding, allowlist, malformed/oversized/denied storage');
})().catch(e=>{console.error(e);process.exitCode=1;});
