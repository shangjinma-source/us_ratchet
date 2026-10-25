const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync(require('path').join(__dirname, '../web/index.html'), 'utf8');
const start = html.indexOf('let currentStrategyValidationSequence = 0;');
const end = html.indexOf("document.addEventListener('DOMContentLoaded'", start);
const body = {html:'',text:'',get innerHTML(){return this.html;},set innerHTML(v){this.html=v;this.text='';},get textContent(){return this.text;},set textContent(v){this.text=v;this.html='';}};
const row = mode => ({mode,label:mode,total_return:1,annualized_return:1.1,max_drawdown:.56});
let payload = {status:'AVAILABLE',research_only:true,execution_blocked:true,independent_oos:false,
  initial_cash:20000,period:{start:'2024-07-31',end:'2025-07-30',calendar_days:364},
  modes:['ACTUAL_EQUITY_FRESH_QUANTITY_MONTHLY','QUANTITY_FROZEN_WEIGHT_REPLAY','TOP1_SAME_PROJECTION_FROZEN_WEIGHT_REPLAY','QQQ_FULL_WEIGHT'].map(row),
  conclusion:'older period',latest_period:{period:{start:'2025-07-31',end:'2026-07-30'},
    modes:['quantity','top1'].map(row),successful_books:2,total_attempts:3,independent_oos:false,
    current_candidate_performance:false,conclusion:'TOP1 高 23.89 个百分点，回撤高 0.14 个百分点',note:'非独立样本外，不是当前推荐收益'}};
const context=vm.createContext({currentPortfolioResearchVersion:'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION',$:()=>body,apiGet:async()=>payload,esc:x=>String(x)});
vm.runInContext(html.slice(start,end),context);
(async()=>{
  await context.loadCurrentStrategyValidation();
  assert.equal((body.innerHTML.match(/<table /g)||[]).length,2);
  assert(body.innerHTML.indexOf('2025-07-31')<body.innerHTML.indexOf('2024-07-31'));
  assert(body.innerHTML.includes('23.89'));
  assert(body.innerHTML.includes('旧 V1 / TOP1'));
  assert(!html.slice(html.indexOf('id="currentStrategyValidation"')-30,html.indexOf('id="currentStrategyValidation"')+80).includes(' open'));
  payload.latest_period.total_attempts=2;
  await context.loadCurrentStrategyValidation();
  assert(body.textContent.includes('暂不可用'));
  context.currentPortfolioResearchVersion='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH';
  await context.loadCurrentStrategyValidation();
  assert(body.textContent.includes('暂不可用'));assert.equal(body.innerHTML,'');
  const actual=require('child_process').spawnSync('D:/python/python.exe',['-X','utf8','-E','-B','-c','import json; from data.verified_daily_comparison import read_verified_daily_comparison; print(json.dumps(read_verified_daily_comparison()))'],{cwd:require('path').join(__dirname,'..'),encoding:'utf8'});
  assert.equal(actual.status,0,actual.stderr);
  const v2=JSON.parse(actual.stdout);assert.equal(v2.status,'AVAILABLE');
  payload=v2;
  let endpoint;context.apiGet=async path=>{endpoint=path;return payload;};
  await context.loadCurrentStrategyValidation();
  assert.equal(endpoint,'/api/verified_daily_comparison');
  assert.equal((body.innerHTML.match(/<table /g)||[]).length,1);
  assert.equal(v2.columns.length,5);assert(body.innerHTML.includes('五方案对比'));
  assert(body.innerHTML.includes('趋势走弱退出、等下次月度选股'));
  assert(body.innerHTML.includes('2024 年内最大回撤'));assert(body.innerHTML.includes('实验未自动替换现行策略'));
  assert(body.innerHTML.includes('138.21%'));assert(body.innerHTML.includes('零费用'));
  assert(body.innerHTML.includes('不是当前分钟限价规则'));assert(!body.innerHTML.includes('131.07%'));
  assert(body.innerHTML.includes('2026 年截至 10/13 收益率'));
  assert(body.innerHTML.includes('非独立样本外'));
  for(const [field,value] of [['schema','TOP1'],['initial_cash',50000],['automatic_promotion',true],['current_minute_execution_validated',true],['columns',[]],['columns',v2.columns.slice(0,3)],['columns',[...v2.columns].reverse()]]){
    payload={...v2,[field]:value};await context.loadCurrentStrategyValidation();
    assert(body.textContent.includes('暂不可用'));assert.equal(body.innerHTML,'');
  }
  payload=JSON.parse(JSON.stringify(v2));payload.columns[0].cagr=Infinity;
  await context.loadCurrentStrategyValidation();assert(body.textContent.includes('暂不可用'));
  payload=v2;
  context.currentPortfolioResearchVersion=null;context.apiGet=async()=>{throw new Error('must not request before version loads');};
  await context.loadCurrentStrategyValidation();assert(body.textContent.includes('等待当前策略版本'));assert.equal(body.innerHTML,'');
  let resolveOld;context.currentPortfolioResearchVersion='CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION';context.apiGet=()=>new Promise(resolve=>{resolveOld=resolve;});
  const late=context.loadCurrentStrategyValidation();
  context.currentPortfolioResearchVersion='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH';
  context.apiGet=async()=>payload;await context.loadCurrentStrategyValidation();
  resolveOld({status:'UNAVAILABLE'});await late;
  assert(body.innerHTML.includes('138.21%'));assert(!body.innerHTML.includes('23.89'));
  let rejectOld;context.apiGet=()=>new Promise((_,reject)=>{rejectOld=reject;});
  const failedLate=context.loadCurrentStrategyValidation();
  context.apiGet=async()=>payload;await context.loadCurrentStrategyValidation();
  rejectOld(new Error('late request failed'));await failedLate;
  assert(body.innerHTML.includes('138.21%'));
  context.apiGet=async()=>{throw new Error('offline');};await context.loadCurrentStrategyValidation();
  assert(body.textContent.includes('暂不可用'));assert.equal(body.innerHTML,'');
  const transitionStart=html.indexOf('if (currentPortfolioResearchVersion !== data.research_version)');
  const transitionEnd=html.indexOf("input.value = String(data.budget);",transitionStart);
  assert(transitionStart>0);
  context.data={research_version:'TOP1'};context.isV2=false;context.syncCurrentResearchNavigation=()=>{};context.resetCurrentPortfolioReview=()=>{};body.open=false;
  vm.runInContext(html.slice(transitionStart,transitionEnd),context);
  assert.equal(body.innerHTML,'');assert(body.textContent.includes('当前方法'));
  console.log('PASS method-bound V2/legacy separation/missing no fallback/budget+execution scope/late response/default collapsed');
})().catch(error=>{console.error(error);process.exitCode=1;});
