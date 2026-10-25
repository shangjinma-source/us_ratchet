// Actual current HTML preference function, synthetic USD broker/cache fixtures.
// No browser, network, account file, storage service or allocation engine access.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const start = 'function loadPlannerPrefs() {';
const end = '\nasync function requestPlannerState()';
assert.equal(html.split(start).length, 2);
assert.equal(html.split(end).length, 2);
const actualFunction = start + html.split(start)[1].split(end)[0];
const session = '2026-10-09';
const clock = Date.parse(session + 'T00:00:00Z');
const brokerFixture = {
  available: true, deployable_cash_usd: 10615.9,
  deployable_cash_session_date: session, deployable_cash_persistence: 'session',
  positions_confirmed_session_date: session, snapshot_clock: new Date(clock).toISOString(),
};
const saved = (changes = {}) => JSON.stringify({
  session_date: session, value: '20000', updated_at: clock + 1000, source: 'manual', ...changes,
});

function run({cache = null, getThrows = false, setThrows = false, broker = {}} = {}) {
  const fixture = {...brokerFixture, ...broker};
  const nodes = {plannerCash: {value: '0'}, plannerBrokerConfirmed: {checked: false}};
  const calls = {reads: 0, writes: 0, stored: null};
  const context = vm.createContext({
    stateData: {broker_account: fixture}, plannerCashSessionDate: null,
    PLANNER_CASH_KEY: 'synthetic_cash_preferences', plannerSnapshotMarketDate: () => session,
    $: id => nodes[id],
    localStorage: {
      getItem(key) {
        assert.equal(key, 'synthetic_cash_preferences'); calls.reads++;
        if (getThrows) throw Error('SYNTHETIC_STORAGE_READ_DENIED');
        return cache;
      },
      setItem(key, value) {
        assert.equal(key, 'synthetic_cash_preferences'); calls.writes++;
        if (setThrows) throw Error('SYNTHETIC_STORAGE_WRITE_DENIED');
        calls.stored = JSON.parse(value);
      },
    },
  });
  vm.runInContext(actualFunction, context);
  context.loadPlannerPrefs();
  return {context, nodes, calls};
}

const cases = [
  ['missing_cache_uses_broker', {}, '10615.9'],
  ['bad_json_uses_broker', {cache: '{broken JSON'}, '10615.9'],
  ['read_denied_uses_broker', {getThrows: true}, '10615.9'],
  ['write_denied_keeps_selection', {setThrows: true}, '10615.9'],
  ['both_denied_use_broker', {getThrows: true, setThrows: true}, '10615.9'],
  ['newer_manual_wins', {cache: saved()}, '20000'],
  ['older_manual_uses_newer_broker', {cache: saved({updated_at: clock - 1})}, '10615.9'],
  ['equal_clock_manual_wins', {cache: saved({updated_at: clock})}, '20000'],
  ['old_session_cache_uses_broker', {cache: saved({session_date: '2026-10-08'})}, '10615.9'],
  ['nonmanual_cache_uses_broker', {cache: saved({source: 'broker_snapshot'})}, '10615.9'],
  ['noncurrent_broker_without_cache_is_zero', {broker: {deployable_cash_session_date: '2026-10-08'}}, '0'],
  ['noncurrent_broker_uses_same_session_saved_fallback', {
    broker: {deployable_cash_session_date: '2026-10-08'}, cache: saved({updated_at: clock - 1}),
  }, '20000'],
  ['until_user_update_keeps_broker_across_session', {
    broker: {deployable_cash_session_date: '2026-10-08', deployable_cash_persistence: 'until_user_update'},
  }, '10615.9'],
];
for (const [name, options, expected] of cases) {
  const result = run(options);
  assert.equal(result.nodes.plannerCash.value, expected, name);
  assert.equal(result.context.plannerCashSessionDate, session, name);
  assert.equal(result.nodes.plannerBrokerConfirmed.checked, true, name);
  assert.equal(result.calls.reads, 1, name);
  assert.equal(result.calls.writes, 1, name);
  if (!options.setThrows) {
    assert.equal(result.calls.stored.value, expected, name);
    assert.equal(result.calls.stored.session_date, session, name);
    assert.deepEqual(Object.keys(result.calls.stored).sort(), ['session_date', 'source', 'updated_at', 'value']);
  }
}

// The existing same-session guard preserves a manual 20000 after storage fails,
// even when a newer broker snapshot arrives. This does not change clock ordering
// during a new session's initial preference selection.
const manual = run({getThrows: true, setThrows: true});
manual.nodes.plannerCash.value = '20000';
manual.context.stateData = {broker_account: {...brokerFixture, deployable_cash_usd: 999,
  snapshot_clock: new Date(clock + 10000).toISOString()}};
manual.context.loadPlannerPrefs();
assert.equal(manual.nodes.plannerCash.value, '20000');
assert.equal(manual.calls.reads, 1);
assert.equal(manual.calls.writes, 1);

process.stdout.write(JSON.stringify({
  status: 'CURRENT_HTML_STORAGE_PREFERENCES_PASS', tests: cases.length + 1,
  synthetic_broker_cash_usd: 10615.9, original_clock_and_session_priority_preserved: true,
  account_or_budget_modified: false, real_browser_layout_verified: false,
}) + '\n');
