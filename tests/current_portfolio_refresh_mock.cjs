// Offline behavioral checks using the actual inline page functions; no network.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
for (const block of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) new vm.Script(block[1]);
const preview = html.slice(html.indexOf('let currentPortfolioChartController ='), html.indexOf('function switchPage(page)'));
const refresh = html.slice(html.indexOf('async function refreshAll()'), html.indexOf('function startStateAutoRefresh()'));
const startup = html.slice(html.indexOf("document.addEventListener('DOMContentLoaded'", html.indexOf('// Load on startup')), html.lastIndexOf('</script>'));
const nodes = new Map();
const node = id => {
  if (!nodes.has(id)) nodes.set(id, {value: id === 'currentPortfolioResearchCash' ? '20000' : '',
    textContent: '', innerHTML: '', style: {}, disabled: false, reportValidity: () => true,
    addEventListener(type, fn) { this[type] = fn; }});
  return nodes.get(id);
};
let start, stateCalls = 0, reviewCalls = 0, autoCalls = 0;
const requests = [];
const assets = [], forwardedV2 = []; let retiredCalls=0,paperInvalidations=0;
const context = vm.createContext({
  currentStrategyValidationSequence: 0,
  window: {fetch(){},StrategyMonthlyTargetUI:{mount(){return {load:async()=>{},setAccount(){},invalidate(){}};}},StrategyAccountUI:{mount(options){options.onRender('',{loaded:true,busy:false,account:null});return {};}}},
  $: node, API_BASE: '', esc: String, URLSearchParams,
  document: {createElement: () => ({remove(){}}), head: {appendChild(script){assets.push(script);}}, addEventListener(type, fn) { assert.equal(type, 'DOMContentLoaded'); start = fn; }},
  apiPost: async route => { assert.equal(route, '/api/refresh'); },
  loadState: async () => { stateCalls++; }, loadReviewPage: async () => { reviewCalls++; },
  arrangePanels: () => {}, startStateAutoRefresh: () => { autoCalls++; },
  fetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve})),
});
vm.runInContext('let researchLoaded=false,researchPageLoaded=false,researchPageGeneration=0,reviewPageLoaded=false,reviewPageGeneration=0,activePage="today";', context);
vm.runInContext(preview + refresh + startup, context);
const tick = () => new Promise(resolve => setImmediate(resolve));
const response = (budget, ticker, id) => ({ok: true, json: async () => ({status: 'AVAILABLE',
  research_version: 'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION', research_only: true,
  execution_blocked: true, research_id: id.repeat(24), as_of: '2026-10-12',
  budget, invested: 10, fees: 0, cash: budget-10, notes: [],
  stocks: [{ticker, units: 1, target_weight: 10/budget, close: 10, notional: 10}]})});
(async () => {
  start(); await tick();
  assert.equal(requests.length, 1, 'startup must POST research exactly once');
  assert.equal(autoCalls, 1);
  requests[0].resolve(response(20000, 'SEED', 'a')); await tick();
  node('currentPortfolioResearchCash').value = '12345.67';
  const refreshPromise = vm.runInContext('refreshAll()', context); await tick();
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(requests[1].options.body).entered_cash, '12345.67');
  assert.equal(node('btnRefresh').disabled, true, 'refresh waits for research response');
  requests[1].resolve(response(12345.67, 'CURRENT', 'b')); await refreshPromise;
  assert.match(node('currentPortfolioPreviewBody').innerHTML, /CURRENT/);
  assert.equal(node('btnRefresh').disabled, false);
  const old = vm.runInContext("loadCurrentPortfolioPreview('10000')", context);
  const newer = vm.runInContext("loadCurrentPortfolioPreview('30000')", context);
  requests[3].resolve(response(30000, 'LATEST', 'd')); await newer;
  requests[2].resolve(response(10000, 'STALE', 'c')); await old;
  assert.match(node('currentPortfolioPreviewBody').innerHTML, /LATEST/);
  assert.doesNotMatch(node('currentPortfolioPreviewBody').innerHTML, /STALE/);
  assert.equal(node('currentPortfolioResearchCash').value, '30000');
  vm.runInContext("activePage='review'", context);
  const review = vm.runInContext('refreshAll()', context); await tick();
  requests[4].resolve(response(30000, 'REVIEW', 'e')); await review;
  assert.equal(reviewCalls, 1);
  assert.equal(stateCalls, 3);
  assert(requests.every(r => r.url === '/api/current_portfolio_research'));
  const allcash = vm.runInContext("loadCurrentPortfolioPreview('0.01')", context);
  requests[5].resolve({ok:true,json:async()=>({...await response(0.01,'NONE','f').json(),status:'ALL_CASH',stocks:[],invested:0,cash:0.01})});
  await allcash;
  assert.match(node('currentPortfolioPreviewBody').innerHTML,/不足买入/);
  assert.doesNotMatch(node('currentPortfolioPreviewBody').innerHTML,/currentPortfolioCharts/);
  const wrong = vm.runInContext("loadCurrentPortfolioPreview('20000')",context);
  requests[6].resolve({ok:true,json:async()=>({...await response(20000,'OLD','a').json(),research_version:'CURRENT_FRESH_QUANTITY_V1_BOUNDED_8192_NO_46_RULES'})});
  await wrong;
  assert.doesNotMatch(node('currentPortfolioPreviewBody').innerHTML,/>OLD</);
  assert.match(node('currentPortfolioPreviewBody').innerHTML,/本次研究候选暂不可用/);
  assert.equal(assets.length,0,'TOP1 must not request new backend static route');
  assert.doesNotMatch(html,/<script src="\/static\/current_quantity_v2_intraday/);
  const v2={...await response(20000,'AAA','b').json(),decision_id:'b'.repeat(64),research_version:'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH',method_version:'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',orders_created:false,executable_buy_quantities:null,invested:30,cash:19970,stocks:[{ticker:'AAA',security_id:'sid-a',units:1,close:10,notional:10,target_weight:0.0005},{ticker:'BBB',security_id:'sid-b',units:1,close:20,notional:20,target_weight:0.001}]};
  let chartLoader,selection,destroyed=0;
  context.window.SelectedStockCharts={createSelectedStockCharts(container,load){chartLoader=load;return {setSelection:s=>selection=s,destroy:()=>destroyed++};}};
  const loadPayload=async data=>{const pending=vm.runInContext("loadCurrentPortfolioPreview('20000')",context);requests.at(-1).resolve({ok:true,json:async()=>data});await pending;};
  context.window.QuantityV2Intraday={setResearch:()=>retiredCalls++,invalidate:()=>{}};
  context.window.QuantityV2Paper={setResearch:d=>forwardedV2.push(d),invalidate:()=>paperInvalidations++};
  await loadPayload(v2);
  assert.equal(assets.length,0);assert.equal(retiredCalls,0);
  assert.equal(node('quantityV2IntradayDetails').hidden,true);assert.equal(node('quantityV2IntradayDetails').style.display,'none');
  assert.match(node('currentPortfolioPreviewBody').innerHTML,/建议限价/);
  assert.equal(forwardedV2.length,1);
  assert.match(node('currentPortfolioPreviewBody').innerHTML,/AAA/);assert.match(node('currentPortfolioPreviewBody').innerHTML,/BBB/);
  assert.match(node('currentPortfolioPreviewTitle').textContent,/V2/);
  node('currentPortfolioChartDetails').toggle({target:{open:true}});assert.equal(selection.stocks.length,2);
  const bars=chartLoader('BBB','day',{});assert.match(requests.at(-1).url,/research_id=bbbbbbbbbbbbbbbbbbbbbbbb/);
  requests.at(-1).resolve({ok:true,json:async()=>({research_id:v2.research_id,research_version:v2.research_version,ticker:'BBB',security_id:'wrong'})});await assert.rejects(bars,/不一致/);
  const late=vm.runInContext("loadCurrentPortfolioPreview('20000')",context);
  node('currentPortfolioResearchCash').value='25000';vm.runInContext('currentPortfolioResearchCashChanged()',context);
  await tick();assert.equal(forwardedV2.length,1,'edited cash must not forward another proposal');assert.ok(paperInvalidations>=2);
  requests.at(-1).resolve({ok:true,json:async()=>v2});await late;assert.match(node('currentPortfolioPreviewBody').textContent,/已修改/);assert.ok(destroyed>0);
  await loadPayload({...v2,stocks:[v2.stocks[0]],invested:10,cash:19990});assert.match(node('currentPortfolioPreviewTitle').textContent,/V2/);await tick();assert.equal(forwardedV2.length,2);assert.equal(forwardedV2[1].stocks.length,1);assert.equal(assets.length,0);assert.equal(retiredCalls,0);
  await loadPayload({...v2,status:'ALL_CASH',stocks:[],invested:0,cash:20000});assert.match(node('currentPortfolioPreviewBody').innerHTML,/保持全现金/);
  await loadPayload({...v2,research_version:'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION'});assert.match(node('currentPortfolioPreviewBody').innerHTML,/暂不可用/);
  let limitCalls=0, releaseQuote;
  context.window.QuantityV2Paper.preview=()=>{limitCalls++;return new Promise(resolve=>{releaseQuote=resolve;});};
  node('currentPortfolioResearchCash').value='20000';
  const oneClick=vm.runInContext('runCurrentPortfolioResearch({preventDefault(){}})',context);
  assert.equal(limitCalls,0,'must await validated configuration before quoting');
  requests.at(-1).resolve({ok:true,json:async()=>v2});await tick();
  assert.equal(limitCalls,1,'explicit configure submits exactly one quote preview');
  assert.equal(node('btnCurrentPortfolioResearch').disabled,true,'configure remains busy until quote completes');
  releaseQuote();await oneClick;assert.equal(node('btnCurrentPortfolioResearch').disabled,false);
  const staleClick=vm.runInContext('runCurrentPortfolioResearch({preventDefault(){}})',context);
  vm.runInContext('currentPortfolioResearchCashChanged()',context);
  requests.at(-1).resolve({ok:true,json:async()=>v2});await staleClick;
  assert.equal(limitCalls,1,'invalidated configuration must never request a quote');
  const incompleteClick=vm.runInContext('runCurrentPortfolioResearch({preventDefault(){}})',context);
  requests.at(-1).resolve({ok:true,json:async()=>({status:'INCOMPLETE'})});await incompleteClick;
  assert.equal(limitCalls,1,'incomplete search must never request a quote');
  await loadPayload(v2);assert.equal(limitCalls,1,'ordinary read/refresh does not silently quote');
  assert.equal(vm.runInContext('currentPortfolioReviewBinding.decision_id',context),v2.decision_id);
  vm.runInContext('reviewPageLoaded=true',context);
  const reviewGeneration=vm.runInContext('reviewPageGeneration',context);
  node('currentPortfolioResearchCash').value='30000';vm.runInContext('currentPortfolioResearchCashChanged()',context);
  assert.equal(vm.runInContext('currentPortfolioReviewBinding',context),null);
  assert.equal(vm.runInContext('reviewPageLoaded',context),false);
  assert.ok(vm.runInContext('reviewPageGeneration',context)>reviewGeneration);
  console.log(JSON.stringify({status:'PASS', inline_script_syntax:true, startup_research_posts:1,
    refresh_current_cash:true, refresh_waits_for_preview:true, late_response_discarded:true,
    review_refresh_preserved:true, real_network_calls:0}));
})().catch(error => { console.error(error); process.exitCode = 1; });
