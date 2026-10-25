import test from 'node:test';
import assert from 'node:assert/strict';
import { bound, publish, validateReceipt } from '../scripts/ndx_dated_comparison_workbook_publish_20261003.mjs';

function fixture() {
  const flags = Object.fromEntries(['formal_comparison_passed', 'future_independent_oos', 'promotion_allowed', 'point_in_time_verified', 'economics_recomputed', 'workbook_created'].map(flag => [flag, false]));
  const reference = { path: 'presentation.json', sha256: 'a'.repeat(64) };
  const input = { path: 'audited_summary.json', sha256: 'b'.repeat(64) };
  const payload = { ...flags, input_references: { summary: input }, source_hashes: { [input.path]: input.sha256 } };
  const publication = { ...flags, schema: 'DATED_COMPARISON_PRESENTATION_PUBLICATION_V1', status: 'PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY', presentation_reference: reference, source_hashes: { ...payload.source_hashes } };
  return [payload, publication, { presentation: reference }];
}

test('refuse before runtime construction while actual pins are missing', async () => {
  const saved = bound.presentation.sha256;
  bound.presentation.sha256 = null;
  try {
    await assert.rejects(publish(), /Explicit execution/);
    await assert.rejects(publish({ execute: true }), /anchors pending/);
  } finally { bound.presentation.sha256 = saved; }
});

test('source receipt verification preserves document bytes and false scope', () => {
  const args = fixture();
  const before = JSON.stringify(args);
  validateReceipt(...args);
  assert.equal(JSON.stringify(args), before);
});

test('reject wrong receipt, uncovered inputs and false-like authority', () => {
  for (const change of [
    args => { args[1].presentation_reference = { ...args[1].presentation_reference, sha256: 'c'.repeat(64) }; },
    args => { args[1].source_hashes.extra = 'c'.repeat(64); },
    args => { args[0].input_references.extra = { path: 'uncovered', sha256: 'c'.repeat(64) }; },
    args => { args[1].future_independent_oos = 0; },
  ]) {
    const args = fixture();
    change(args);
    assert.throws(() => validateReceipt(...args));
  }
});
