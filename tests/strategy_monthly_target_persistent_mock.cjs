const assert=require('node:assert/strict');
const {createController,render}=require('../web/strategy_monthly_target.js');
const account={revision:'r1',cash_confirmation_valid:false,holdings:[{security_id:'S',ticker:'SNDK',quantity:14}],orders:[]};
const target={status:'SAVED_TARGET',target_id:'t1',target_month:'2026-10',targets:[{security_id:'S',ticker:'SNDK',quantity:14}]};
const preview={status:'READY',target_id:'t1',account_revision:'r1',reference_valid_until:null,difference:{new_orders:[]},reference_quotes:{S:{ticker:'SNDK',buy_limit:null,sell_limit:'1350',observed_at:'2026-10-16T15:00:00Z',reference_valid_until:'2026-10-16T15:02:00Z',sell_is_exit_reference:true}}};
(async()=>{
 let html=render({loaded:true,account,target:null});assert(html.includes('SNDK'));assert(html.includes('14'));assert(html.includes('待配置'));assert(html.includes('确认最新余额'));assert(!html.includes('目标 14'));
 html=render({loaded:true,account,target});assert(html.includes('待刷新'));assert(html.includes('SNDK'));
 const ready={...account,cash_confirmation_valid:true};let clock=Date.parse('2026-10-16T15:01:00Z'),fail=false;
 const c=createController({now:()=>clock,fetchImpl:async url=>{if(fail)throw Error('offline');return {ok:true,json:async()=>url.endsWith('preview')?preview:target};}});
 c.setAccount(ready);await c.load();await c.refresh();html=render(c.getState());assert(html.includes('持有；本次无需新增订单'));assert(html.includes('$1,350'));assert(!html.includes('不是止盈信号'));assert(html.includes('待刷新'));
 clock+=120000;html=render({...c.getState(),renderedAt:clock});assert(html.includes('旧参考，待刷新；不可作为有效单'));
 fail=true;await assert.rejects(c.refresh());assert(render(c.getState()).includes('$1,350'));assert(!c.getState().fresh);
 c.setAccount({...account,revision:'r2'});html=render(c.getState());assert(html.includes('SNDK'));assert(!html.includes('$1,350'));assert(html.includes('确认最新余额'));
 html=render({loaded:true,target,account:{...ready,orders:[{security_id:'S',ticker:'SNDK',side:'BUY',remaining_quantity:9}]},preview,fresh:true,renderedAt:Date.parse('2026-10-16T15:01:00Z')});assert(html.includes('9 / 0'));assert(html.includes('不重复下单'));
 html=render({loaded:true,target,account:ready,preview:{...preview,reference_quotes:{S:{buy_limit:'NaN',sell_limit:'<script>'}}},fresh:true});assert(!html.includes('<script>'));assert(!html.includes('$NaN'));
 c.dispose();console.log('PASS persistent holdings/targets, invalid cash, no target, reference-only prices, stale retention and revision reset');
})().catch(e=>{console.error(e);process.exitCode=1;});
