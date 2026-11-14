const assert = require('node:assert/strict');
const {createController, browserPendingStore} = require('../web/strategy_roa_controller.js');

(async () => {
  const memory = new Map();
  const storage = {
    getItem: key => memory.get(key) ?? null,
    setItem: (key, value) => memory.set(key, value),
    removeItem: key => memory.delete(key)
  };
  const calls = [];
  let writes = 0;
  let savedIntent;
  const request = async (path, body) => {
    calls.push(path);
    if (path.endsWith('cash-save-and-preview')) {
      writes++;
      savedIntent = structuredClone(body);
      // Persistence succeeded, but its HTTP response did not reach the browser.
      throw Error('NETWORK_LOST');
    }
    if (path.endsWith('cash-status')) {
      assert.deepEqual(body, savedIntent);
      return {cash_saved: true, advice_ready: false};
    }
    assert.ok(path.endsWith('advice-retry'));
    return {cash_saved: null, advice_ready: true, account_revision: 'b'.repeat(64),
      account: {revision: 'b'.repeat(64)}, strategy_epoch: 'test',
      strategy_kind: 'ROA_DEFENSIVE_V1', status: 'HOLD', executable: false, rows: []};
  };
  let ids = 0;
  const browser = () => createController({request,
    readAccount: async () => ({revision: 'a'.repeat(64)}),
    eventId: () => `cash-${++ids}`, expectedEpoch: 'test',
    pendingStore: browserPendingStore(storage, 'same-account-epoch')});
  const beforeReload = browser();
  await beforeReload.save('5544.73');
  assert.equal(beforeReload.getState().cashSaved, null);
  const afterReload = browser();
  await afterReload.load();
  assert.equal(afterReload.getState().error, 'CASH_RECONCILIATION_REQUIRED');
  await afterReload.save('6000');
  assert.equal(writes, 1);
  await afterReload.refresh();
  assert.equal(afterReload.getState().error, null);
  assert.equal(afterReload.getState().cashSaved, true);
  assert.equal(afterReload.getState().advice.status, 'HOLD');
  assert.equal(afterReload.getState().pending, null);
  assert.deepEqual(calls.map(path => path.split('/').pop()),
    ['cash-save-and-preview', 'cash-status', 'advice-retry']);
  assert.equal(writes, 1);
  assert.equal(ids, 1);
  console.log('PASS: reload reconciles the original cash write without resubmission');
})().catch(error => { console.error(error); process.exitCode = 1; });
