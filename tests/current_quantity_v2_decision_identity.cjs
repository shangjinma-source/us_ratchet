const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
const source=html.slice(html.indexOf('function currentPortfolioResearchCashChanged()'),html.indexOf('function openCurrentPlanReview()'));
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'100',disabled:false,style:{},reportValidity:()=>true});return nodes.get(id);}
let pending=[],paperSeen=[],invalidations=0,paperInvalidations=0;
const context={console,Number,String,Math,Set,Array,URLSearchParams,
  currentStrategyValidationSequence:0,currentPortfolioResearchVersion:null,
  $:node,esc:String,API_BASE:'',currentPortfolioPreviewSequence:0,currentPortfolioChartController:null,currentPortfolioDisplayedBudget:null,
  window:{ResearchPaper:{invalidate(){invalidations++;},setResearch(){}},QuantityV2Intraday:{invalidate(){invalidations++;}},QuantityV2Paper:{invalidate(){paperInvalidations++;},setResearch(data){paperSeen.push(structuredClone(data));}}},
  fetch:(url,options)=>new Promise(resolve=>pending.push({resolve,options}))};
vm.createContext(context);vm.runInContext(source,context);
const fixture=(cash=100,id='a'.repeat(64))=>({status:'ALL_CASH',research_version:'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH',
  decision_id:id,research_id:id.slice(0,24),method_version:'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',
  orders_created:false,executable_buy_quantities:null,research_only:true,execution_blocked:true,
  stocks:[],budget:cash,invested:0,fees:0,cash,as_of:'2026-10-13',notes:[]});
async function resolveRequest(promise,data){pending.shift().resolve({ok:true,json:async()=>data});await promise;}
(async()=>{
  await resolveRequest(context.loadCurrentPortfolioPreview('100'),fixture());
  assert.equal(paperSeen.length,1);assert.equal(paperSeen[0].decision_id,'a'.repeat(64));
  for(const change of [d=>delete d.decision_id,d=>d.decision_id='b'.repeat(64),d=>d.decision_id='a'.repeat(24)]){
    const bad=fixture();change(bad);await resolveRequest(context.loadCurrentPortfolioPreview('100'),bad);
    assert.equal(paperSeen.length,1);assert.match(node('currentPortfolioPreviewBody').innerHTML,/暂不可用/);
  }
  const old=context.loadCurrentPortfolioPreview('100');
  node('currentPortfolioResearchCash').value='200';context.currentPortfolioResearchCashChanged();
  const newer=context.loadCurrentPortfolioPreview('200');
  const oldReply=pending.shift();const newReply=pending.shift();
  newReply.resolve({ok:true,json:async()=>fixture(200,'b'.repeat(64))});await newer;
  oldReply.resolve({ok:true,json:async()=>fixture()});await old;
  assert.equal(paperSeen.length,2);assert.equal(paperSeen[1].budget,200);assert.equal(paperSeen[1].decision_id,'b'.repeat(64));
  assert.equal(node('currentPortfolioResearchCash').value,'200');assert.ok(invalidations>=2);
  assert.equal(paperSeen.length,2);assert.equal(paperSeen[1].decision_id,'b'.repeat(64));assert.ok(paperInvalidations>=2);
  console.log('PASS actual dashboard: full decision identity, wrong/missing identity rejected, edited cash invalidates and late old reply ignored');
})().catch(error=>{console.error(error);process.exitCode=1;});
