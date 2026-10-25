const assert=require('node:assert/strict');
const {create,amount}=require('../web/current_research_paper.js');
const research={research_version:'CURRENT_FRESH_QUANTITY_V1_BOUNDED_8192_NO_46_RULES',research_only:true,execution_blocked:true,research_id:'a'.repeat(24)};
const payload={genesis_plan_id:'a'.repeat(64),genesis_research_id:research.research_id,research_only:true,execution_blocked:true,market_session:{date:'2030-01-02',timezone:'America/New_York',open_at:'09:30',close_at:'16:00'},account_id:'paper-'+'a'.repeat(24),review:null,plan:{research_id:research.research_id,plan_id:'a'.repeat(64),research_only:true,execution_blocked:true,adopted:false,active_date:'2030-01-02',available_cash:'100',reserved_cash:'30',unreserved_cash:'70',orders:[{order_id:'o1',ticker:'A',security_id:'a',side:'BUY',quantity:3,limit:'10'}]}};
function setup(chartsApi,initiallyOpen=false){
 const calls=[],pending=[],listeners={}; let actions=[];
 const details={open:initiallyOpen,addEventListener:(k,f)=>listeners[k]=f};
 const chartDetails={open:false,addEventListener:(k,f)=>chartDetails[k]=f},chartBody={};
 const body={textContent:'',_html:'',set innerHTML(v){this._html=v;actions=[...v.matchAll(/data-action="([^"]+)"/g)].map(m=>({dataset:{action:m[1]},disabled:false,addEventListener:(k,f)=>{if(k==='click')this['click_'+m[1]]=f;}}));},get innerHTML(){return this._html;},querySelectorAll:s=>actions,querySelector:s=>s==='#paperPlanCharts' && body._html.includes('id="paperPlanCharts"') ? chartDetails : s==='#paperPlanChartBody' ? chartBody : null};
 const component=create({getElementById:id=>id==='researchPaperDetails'?details:body},(url,opts)=>{calls.push({url,opts});return new Promise(resolve=>pending.push(resolve));},()=> 'uuid',chartsApi);
 return {component,body,details,calls,chartDetails,open(){details.open=true;listeners.toggle();},respond(data=payload,ok=true){pending.shift()({ok,json:async()=>data});},actions:()=>actions};
}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const openStates=[];globalThis.ResearchIntraday={create:()=>({setOpen:v=>openStates.push(v),setResearch:()=>{},invalidate:()=>{}})};const initially=setup(undefined,true);assert.deepEqual(openStates,[true]);delete globalThis.ResearchIntraday;
 assert.equal(amount('12345/100'),'123.45'); for(const v of ['1/0','<img>','NaN','-1']) assert.throws(()=>amount(v));
 const top=setup();top.component.setResearch({...research,research_version:'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION',status:'AVAILABLE',as_of:'2026-10-13',stocks:[{ticker:'SNDK',units:20,close:987.99}]});top.open();assert.equal(top.calls.length,1);assert.ok(top.calls[0].url.endsWith('/preview'));assert.deepEqual(JSON.parse(top.calls[0].opts.body),{research_id:research.research_id});top.respond();await tick();assert.match(top.body.innerHTML,/开启模拟记录/);assert.match(top.body.innerHTML,/封存模拟限价/);assert.match(top.body.innerHTML,/不随盘中更新/);assert.match(top.body.innerHTML,/决策日/);
 const forwarded=[];let cleared=0;
 globalThis.ResearchIntraday={create:()=>({setOpen:()=>{},setResearch:d=>forwarded.push(d.research_version),invalidate:()=>cleared++})};
 globalThis.ResearchIntradayPaper={create:()=>({setParentOpen:()=>{},isOpen:()=>false,suspend:()=>{},setResearch:d=>forwarded.push(d.research_version),invalidate:()=>cleared++})};
 const isolated=setup();isolated.component.setResearch({...research,research_version:'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION'});isolated.open();
 isolated.component.setResearch({...research,research_version:'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'});isolated.respond();await tick();isolated.open();
 assert.equal(isolated.calls.length,1);assert.equal(forwarded.length,2);assert.ok(cleared>=4);assert.match(isolated.body.textContent,/V2.*新组合限价与模拟记录/);assert.doesNotMatch(isolated.body.innerHTML,/开启模拟记录/);
 delete globalThis.ResearchIntraday;delete globalThis.ResearchIntradayPaper;
 let x=setup();x.component.setResearch(research);assert.equal(x.calls.length,0);x.open();assert.equal(x.calls.length,1);assert.ok(x.calls[0].url.endsWith('/preview'));x.open();assert.equal(x.calls.length,1);
 x.component.invalidate();x.respond();await tick();assert.match(x.body.textContent+x.body.innerHTML,/变化/);assert.equal(x.body.innerHTML,'');
 x=setup();x.component.setResearch({...research,research_version:'OLD'});x.open();assert.equal(x.calls.length,0);
 x=setup();x.component.setResearch(research);x.open();x.respond({...payload,plan:{...payload.plan,research_id:'b'.repeat(24)}});await tick();assert.match(x.body.textContent+x.body.innerHTML,/不一致/);
 x=setup();x.component.setResearch(research);x.open();x.respond();await tick();assert.match(x.body.innerHTML,/开启模拟记录/);assert.equal(x.calls.length,1);assert.equal(x.calls[0].opts.method,'POST');assert.deepEqual(JSON.parse(x.calls[0].opts.body),{research_id:research.research_id});
 x.body.click_start();x.body.click_start();assert.equal(x.calls.length,2);assert.ok(x.actions().every(a=>a.disabled));assert.deepEqual(JSON.parse(x.calls[1].opts.body),{research_id:research.research_id,expected_plan_id:'a'.repeat(64)});
 x.component.invalidate();x.respond();await tick();assert.match(x.body.textContent+x.body.innerHTML,/变化/);
 x=setup();x.component.setResearch(research);x.open();
 const review={research_only:true,execution_blocked:true,adopted:false,account_id:'paper-'+'a'.repeat(24),plan_id:'a'.repeat(64),research_id:research.research_id,revision:'r1',cash:'100',reserved_cash:'30',unreserved_cash:'70',total_recorded_fees:'0',shares:{},orders:[{order_id:'o1',filled_quantity:0,unfilled_quantity:3,order_status:'OPEN'}]};
 x.respond({...payload,review});await tick();assert.match(x.body.innerHTML,/实际费用（必填）/);assert.doesNotMatch(x.body.innerHTML,/开启模拟记录/);
 x.body.click_restore();assert.equal(x.calls[1].opts.method,'GET');assert.equal(x.calls[1].opts.body,undefined);assert.match(x.calls[1].url,/account\?account_id=paper-a/);
 x.respond({...payload,review:{...review,plan_id:'other'}});await tick();assert.match(x.body.textContent+x.body.innerHTML,/不一致/);
 const successor={...payload,plan:{...payload.plan,plan_id:'c'.repeat(64),research_id:'c'.repeat(24)},review:{...review,plan_id:'c'.repeat(64),research_id:'c'.repeat(24)}};
 x=setup();x.component.setResearch(research);x.open();x.respond(successor);await tick();assert.match(x.body.innerHTML,/查看本计划触价复盘/);
 x.body.click_restore();x.respond(successor);await tick();assert.match(x.body.innerHTML,/查看本计划触价复盘/);
 for(const invalid of [{...successor,account_id:'paper-wrong'}, {...successor,genesis_research_id:'b'.repeat(24)}, {...successor,genesis_plan_id:'b'.repeat(64),account_id:'paper-'+'b'.repeat(24)}]) {
   x=setup();x.component.setResearch(research);x.open();x.respond(successor);await tick();
   x.body.click_restore();x.respond(invalid);await tick();assert.match(x.body.textContent+x.body.innerHTML,/谱系不一致/);
 }
 x=setup();x.component.setResearch(research);x.open();x.respond(successor);await tick();x.body.click_restore();x.component.invalidate();x.respond(successor);await tick();assert.match(x.body.textContent+x.body.innerHTML,/变化/);
 const market_review={plan_id:'a'.repeat(64),research_id:research.research_id,revision:'r1',observed_through:'2030-01-02',orders:[{...review.orders[0],observed_touch:'UNKNOWN',reason:'行情未完整'}]};
 x=setup();x.component.setResearch(research);x.open();x.respond({...payload,review});await tick();
 x.body.click_review();assert.match(x.calls[1].url,/review\?account_id=paper-a/);assert.equal(x.calls[1].opts.method,'GET');
 x.respond({...payload,review,market_review});await tick();assert.match(x.body.innerHTML,/待完整行情/);assert.match(x.body.innerHTML,/日线触价不代表成交/);
 assert.match(x.body.innerHTML,/行情状态待核/);assert.doesNotMatch(x.body.innerHTML,/行情未完整/);
 for(const [reason,label] of Object.entries({ORDER_SESSION_AFTER_OBSERVATION_CUTOFF:'尚无该交易日的完整行情',MATCHING_COMPLETED_SESSION_BAR_MISSING:'缺少对应交易日行情',COMPLETED_DAILY_RANGE_ONLY:'仅按当日高低价判断'})) {
   x.body.click_review();x.respond({...payload,review,market_review:{...market_review,orders:[{...market_review.orders[0],reason}]}});await tick();assert.ok(x.body.innerHTML.includes(label));assert.ok(!x.body.innerHTML.includes(reason));
 }
 x.body.click_restore();x.respond({...payload,review});await tick();assert.doesNotMatch(x.body.innerHTML,/日线触价不代表成交/,'responses without market_review clear the old review');
 for(const invalid of [{...market_review,revision:'old'}, {...market_review,orders:[{...market_review.orders[0],order_id:'other'}]}, {...market_review,orders:[{...market_review.orders[0],observed_touch:'MAYBE'}]}, {...market_review,orders:[market_review.orders[0],market_review.orders[0]]}]) {
   x=setup();x.component.setResearch(research);x.open();x.respond({...payload,review,market_review:invalid});await tick();assert.match(x.body.textContent+x.body.innerHTML,/触价复盘版本或订单不一致/);
 }
 x=setup();x.component.setResearch(research);x.open();x.respond({message:'MARKET_NOT_OPEN: 尚未开盘'},false);await tick();assert.match(x.body.textContent+x.body.innerHTML,/MARKET_NOT_OPEN: 尚未开盘/);assert.equal(x.calls.length,1,'server rejection must not auto-retry');
 const html=require('fs').readFileSync(require('path').join(__dirname,'../web/index.html'),'utf8');
 let chartLoad,selection,destroyed=0;
 const chartApi={createSelectedStockCharts(container,load){chartLoad=load;return {setSelection:s=>selection=s,destroy:()=>destroyed++};}};
 const chartPayload={...payload,review:{...review,shares:{b:2}},plan:{...payload.plan,signal_asof:'2030-01-01',target_quantities:{a:3,c:0},causal_inputs:{securities:{a:'A',b:'B',c:'C'}}}};
 x=setup(chartApi);x.component.setResearch(research);x.open();x.respond(chartPayload);await tick();
 x.chartDetails.open=true;x.chartDetails.toggle();assert.deepEqual(selection.stocks.map(s=>s.ticker),['A','B']);assert.ok(selection.stocks.every(s=>s.limit===undefined));
 let loading=chartLoad('B','week',new AbortController().signal);assert.match(x.calls[1].url,/security_id=b/);assert.match(x.calls[1].url,/expected_plan_id=/);
 x.respond({status:'AVAILABLE',account_id:payload.account_id,plan_id:payload.plan.plan_id,research_id:research.research_id,security_id:'b',ticker:'B',interval:'week',daily_as_of:'2030-01-01',research_only:true,execution_blocked:true,bars:[]});await loading;
 loading=chartLoad('B','day',new AbortController().signal);x.respond({account_id:'wrong'});await assert.rejects(loading,/版本不一致/);
 loading=chartLoad('B','day',new AbortController().signal);x.component.invalidate();x.respond({});await assert.rejects(loading,/失效/);assert.ok(destroyed>0);
 const input={account_id:payload.account_id,expected_revision:'r1',current_revision:'r1',parent_plan_id:payload.plan.plan_id,input_id:'input1',research_only:true,execution_blocked:true};
 const proposal={...successor,review:undefined,current_revision:'r1',expected_revision:'r1',input_id:'input1',preview_id:'preview1',route:{action:'ROLL'},market_session:{date:'2030-01-03',timezone:'America/New_York',open_at:'2030-01-03T09:30:00-05:00',close_at:'2030-01-03T16:00:00-05:00'},plan:{...successor.plan,causal_inputs:{},account_revision:'r1',signal_asof:'2030-01-02',active_date:'2030-01-03',target_quantities:{a:3}}};
 x=setup();x.component.setResearch(research);x.open();x.respond({...payload,review});await tick();
 x.body.click_successor();x.body.click_successor();assert.equal(x.calls.length,2);assert.match(x.calls[1].url,/successor\/input/);assert.equal(x.calls[1].opts.method,'GET');
 x.respond(input);await tick();assert.equal(x.calls.length,3);assert.deepEqual(JSON.parse(x.calls[2].opts.body),{account_id:payload.account_id,input_id:'input1',expected_revision:'r1'});
 x.respond(proposal);await tick();assert.match(x.body.innerHTML,/尚未采用/);assert.match(x.body.innerHTML,/月内目标不变/);assert.match(x.body.innerHTML,/计划版本 aaaaaaaaaaaa/);
 x.body.click_adopt();x.body.click_adopt();assert.equal(x.calls.length,4);assert.deepEqual(JSON.parse(x.calls[3].opts.body),{account_id:payload.account_id,preview_id:'preview1',event_id:'uuid',expected_revision:'r1'});
 x.respond(successor);await tick();assert.doesNotMatch(x.body.innerHTML,/尚未采用/);assert.match(x.body.innerHTML,/计划版本 cccccccccccc/);
 x.body.click_successor();x.respond({message:'缺少已登记行情'},false);await tick();assert.match(x.body.innerHTML,/缺少已登记行情/);assert.match(x.body.innerHTML,/计划版本 cccccccccccc/);
 x.body.click_successor();x.component.invalidate();x.respond(input);await tick();assert.match(x.body.textContent,/变化/);assert.equal(x.calls.length,6,'invalidated input must not start preview');
 assert.match(html,/function currentPortfolioResearchCashChanged\(\) \{\s+if \(window.ResearchPaper\) window.ResearchPaper.invalidate\(\)/);
 assert.match(html,/async function loadCurrentPortfolioPreview[^\n]+\{\s+if \(window.ResearchPaper\) window.ResearchPaper.invalidate\(\)/);
 assert.match(html,/ResearchPaper.setResearch\(data\)/);
 console.log('PASS: lazy preview/read-only, cash invalidation, stale response, version guard, duplicate start, amount parsing, index hooks');
})().catch(e=>{console.error(e);process.exitCode=1;});
