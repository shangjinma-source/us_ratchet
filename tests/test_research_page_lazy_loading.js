// Behavioral checks against extracted production functions, no network or account.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const between = (start, end) => html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start)));
const functions = between('function switchPage(page)', 'async function toggleResearchCenter')
  + between('function loadResearchPage()', 'function startStateAutoRefresh');
const loaders = ['loadSecurityCandidatePool', 'loadNdxCompetition', 'loadNdxMarginalAllocation',
  'loadNdxPortfolioCurves', 'loadNdxStyleCrowding', 'loadResearchCandidates',
  'loadTacticalQuality', 'loadGoldenPitReview', 'loadBacktest'];
function fixture() {
  const calls = [];
  const button = { disabled: false, textContent: '' };
  const context = vm.createContext({
    activePage: 'today', researchLoaded: false, researchPageLoaded: false,
    researchPageLoadPromise: null, researchPageGeneration: 0,
    $: () => button,
    document: { querySelectorAll: () => [], body: { classList: { contains: () => true } } },
    apiPost: async () => { calls.push('clear-cache'); },
    loadState: async () => { calls.push('state'); },
    showError: message => { calls.push(message); },
  });
  for (const name of loaders) context[name] = async () => { calls.push(name); };
  vm.runInContext(functions, context);
  return { calls, button, context };
}
async function main() {
  const daily = fixture();
  await daily.context.refreshAll();
  assert.deepEqual(daily.calls, ['clear-cache', 'state']);
  assert.equal(daily.button.disabled, false);
  daily.context.switchPage('account');
  assert.deepEqual(daily.calls, ['clear-cache', 'state']);

  daily.context.switchPage('research');
  await daily.context.loadResearchPage();
  assert.equal(daily.calls.filter(name => name.startsWith('load')).length, 8);
  daily.context.switchPage('today');
  daily.context.switchPage('research');
  await daily.context.loadResearchPage();
  assert.equal(daily.calls.filter(name => name.startsWith('load')).length, 8);

  const delayed = fixture();
  let release;
  delayed.context.loadSecurityCandidatePool = () => new Promise(resolve => { release = resolve; });
  const first = delayed.context.loadResearchPage();
  await delayed.context.refreshAll(); // Daily page is not blocked by hidden research.
  delayed.context.loadSecurityCandidatePool = async () => { delayed.calls.push('new-pool'); };
  release();
  await first;
  assert.equal(delayed.context.researchPageLoaded, false); // Old response cannot mark new generation loaded.
  delayed.context.switchPage('research');
  await delayed.context.loadResearchPage();
  assert.equal(delayed.context.researchPageLoaded, true);
  assert.equal(delayed.calls.filter(name => name === 'new-pool').length, 1);

  const failed = fixture();
  failed.context.loadState = async () => { throw new Error('offline state failure'); };
  await assert.rejects(failed.context.refreshAll(), /offline state failure/);
  assert.equal(failed.button.disabled, false);
  console.log('PASS: daily/account do not fetch hidden research; explicit navigation loads once; stale generation rejected; refresh failure unlocks button');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
