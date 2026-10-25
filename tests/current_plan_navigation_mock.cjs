const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
assert.match(html,/<div class="card" id="panelExecutiveBrief" hidden style="display:none !important">/);
assert.match(html,/<details class="card" id="panelGoldenPit">/);
assert.doesNotMatch(html,/<details[^>]*id="panelGoldenPit"[^>]*\bopen\b/);
assert.match(html,/account: \['panelOps', 'panelHoldings'\]/);
assert.match(html,/review: \['panelCurrentPlanReview', 'panelGoldenPit'\]/);
let page,scrolled=false;const details={open:false,scrollIntoView(){scrolled=true;}};
const code=html.slice(html.indexOf('function openCurrentPlanReview()'),html.indexOf('function switchPage(page)'));
const c=vm.createContext({switchPage:p=>page=p,$:id=>id==='researchPaperDetails'?details:null});
vm.runInContext(code+'openCurrentPlanReview();',c);
assert.equal(page,'today');assert.equal(details.open,true);assert.equal(scrolled,true);
assert.match(html,/日线触价不代表成交/);
console.log('PASS: hidden legacy execution, collapsed legacy review, current-plan navigation, account access preserved');

// Real dashboard functions: both asynchronous completion orders preserve V2 access.
const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{style:{},hidden:false,open:false,textContent:'',innerHTML:'',scrollIntoView(){this.scrolled=true;}});return nodes.get(id);}
let holds;
const n=vm.createContext({$:node,currentPortfolioResearchVersion:null,stateData:{initialized:false,broker_account:{positions:[{ticker:'NEW',shares:2}]}},switchPage:p=>page=p,
 requestPlannerState:async()=>true,loadPlannerPrefs(){},clearError(){},renderExecutiveBrief(){},renderBuyPlan(){},renderHoldings:(s,b)=>holds=b,populateTickerSelectors(){},showError:e=>{throw Error(e);},Date});
vm.runInContext(code+html.slice(html.indexOf('async function loadState()'),html.indexOf('function renderExecutiveBrief(data)')),n);
(async()=>{
 await n.loadState();assert.equal(node('btnInit').style.display,'inline-flex');assert.equal(node('panelOps').style.display,'none');
 n.currentPortfolioResearchVersion='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH';n.syncCurrentResearchNavigation();
 assert.equal(node('btnInit').style.display,'none');assert.equal(node('panelOps').style.display,'block');assert.equal(node('researchPaperDetails').hidden,true);
 assert.match(node('currentPlanReviewDescription').textContent,/不是完整绩效复盘/);n.openCurrentPlanReview();assert.equal(node('quantityV2PaperDetails').open,true);assert.equal(node('quantityV2PaperDetails').scrolled,true);assert.equal(node('researchPaperDetails').open,false);
 await n.loadState();assert.equal(node('btnInit').style.display,'none');assert.equal(node('panelOps').style.display,'block');assert.equal(holds.positions[0].ticker,'NEW');
 n.currentPortfolioResearchVersion='CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION';n.syncCurrentResearchNavigation();assert.equal(node('researchPaperDetails').hidden,false);assert.equal(node('btnInit').style.display,'inline-flex');n.openCurrentPlanReview();assert.equal(node('researchPaperDetails').open,true);
 console.log('PASS actual loadState/navigation: V2 never initializes legacy strategy; actual holdings remain accessible, record-only review route, legacy fallback preserved');
})().catch(e=>{console.error(e);process.exitCode=1;});
