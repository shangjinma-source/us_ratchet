import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { bound, publish, validateReceipt } from '../scripts/ndx_dated_comparison_workbook_publish_20261003.mjs';

function receipt() {
  const flags = Object.fromEntries(['formal_comparison_passed', 'future_independent_oos', 'promotion_allowed', 'point_in_time_verified', 'economics_recomputed', 'workbook_created'].map(name => [name, false]));
  const inputs = Object.fromEntries(['summary', 'publication', 'audit', 'reader', 'adapter'].map(name => [name, { path: `synthetic-${name}`, sha256: 'a'.repeat(64) }]));
  const references = { presentation: { path: 'synthetic-presentation', sha256: 'b'.repeat(64) } };
  const payload = { schema: 'SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1', ...flags, input_references: inputs, source_hashes: Object.fromEntries(Object.values(inputs).map(r => [r.path, r.sha256])) };
  const publication = { schema: 'DATED_COMPARISON_PRESENTATION_PUBLICATION_V1', status: 'PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY', ...flags, presentation_reference: structuredClone(references.presentation), source_hashes: structuredClone(payload.source_hashes) };
  return [payload, publication, references];
}

test('pending anchors and false execute never perform input reads or mkdir', async () => {
  const read = fs.readFile, mkdir = fs.mkdir;
  const pin = bound.presentation.sha256;
  bound.presentation.sha256 = null;
  fs.readFile = async () => assert.fail('Must not read any file');
  fs.mkdir = async () => assert.fail('Must not create a directory');
  try {
    await assert.rejects(publish({ execute: 1 }), /Explicit execution/);
    await assert.rejects(publish({ execute: true }), /anchors pending/);
  } finally { fs.readFile = read; fs.mkdir = mkdir; bound.presentation.sha256 = pin; }
});

test('all direct role hashes and receipt target stay linked without mutation', () => {
  const original = receipt(); const before = JSON.stringify(original);
  validateReceipt(...original); assert.equal(JSON.stringify(original), before);
  for (const role of ['summary', 'publication', 'audit', 'reader', 'adapter']) {
    const args = receipt(); args[0].input_references[role].sha256 = 'f'.repeat(64);
    assert.throws(() => validateReceipt(...args));
  }
  for (const change of [
    a => { a[1].presentation_reference.path = 'other-task'; },
    a => { a[1].source_hashes.extra = 'c'.repeat(64); },
    a => { a[0].workbook_created = true; },
    a => { a[1].formal_comparison_passed = 0; },
  ]) { const args = receipt(); change(args); assert.throws(() => validateReceipt(...args)); }
});

test('loaded publisher bytes cannot be replaced by a fresh disk self hash', async () => {
  const source = fileURLToPath(new URL('../scripts/ndx_dated_comparison_workbook_publish_20261003.mjs', import.meta.url));
  const saved = structuredClone(bound), read = fs.readFile, mkdir = fs.mkdir;
  const blobs = new Map();
  for (const [role, value] of Object.entries(bound)) {
    const bytes = Buffer.from(role);
    blobs.set(value.path, bytes);
    value.sha256 = createHash('sha256').update(bytes).digest('hex');
  }
  let otherReads = 0;
  fs.readFile = async file => {
    if (String(file) === source) return Buffer.from('changed bytes after module load');
    otherReads += 1;
    assert.ok(blobs.has(String(file)));
    return blobs.get(String(file));
  };
  fs.mkdir = async () => assert.fail('No output under source drift');
  try {
    await assert.rejects(publish({ execute: true }), /Source drift|Loaded.*source|loaded.*source/);
    assert.equal(otherReads, Object.keys(bound).length);
  } finally {
    fs.readFile = read; fs.mkdir = mkdir;
    for (const role of Object.keys(bound)) bound[role] = saved[role];
  }
});
