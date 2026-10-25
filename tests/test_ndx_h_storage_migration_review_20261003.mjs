import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {resourceGate, OUTPUT, BOUND} from '../scripts/ndx_dated_workbook_extension_publish_20261003.mjs';

const source = await fs.readFile(new URL('../scripts/ndx_dated_workbook_extension_publish_20261003.mjs', import.meta.url), 'utf8');
const reserve = 5n * 1024n ** 3n;

test('new data and output use D, authenticated code remains E; no joined drive token', () => {
  assert.equal(path.parse(OUTPUT).root.toUpperCase(), 'D:\\');
  for (const key of ['index', 'publication', 'audit', 'tasks', 'shared', 'classification'])
    assert.equal(path.parse(BOUND[key].path).root.toUpperCase(), 'D:\\');
  for (const key of ['core', 'native_helper', 'path_component', 'data_producer'])
    assert.equal(path.parse(BOUND[key].path).root.toUpperCase(), 'E:\\');
  assert(!OUTPUT.includes('E:\\'));
  assert(source.indexOf('await resourceGate(OUTPUT)') < source.indexOf('return executeDelivery({state'));
});

test('absent target probes only existing same-volume ancestors and never mkdir', async t => {
  const calls = [];
  t.mock.method(fs, 'mkdir', async () => { throw Error('must not create directory'); });
  t.mock.method(fs, 'statfs', async (p, options) => {
    calls.push(p); assert.equal(options.bigint, true);
    if (p !== 'D:\\') throw Object.assign(Error('missing'), {code: 'ENOENT'});
    return {bavail: reserve, bsize: 1n};
  });
  await resourceGate('D:/uncreated-h-review/deeper');
  assert.deepEqual(calls, ['D:\\uncreated-h-review\\deeper', 'D:\\uncreated-h-review', 'D:\\']);
});

test('target-volume free space plus exact reserve decides, unrelated E cannot rescue D', async t => {
  let available = reserve + 127n;
  t.mock.method(fs, 'statfs', async p => {
    assert.equal(path.parse(p).root.toUpperCase(), 'D:\\');
    return {bavail: available, bsize: 1n};
  });
  await assert.rejects(resourceGate('D:/target', 128), /RESOURCE_STOP/);
  available++;
  await resourceGate('D:/target', 128);
  await assert.rejects(resourceGate('D:/target', -1), /Exact safe integer/);
});

test('actual private collector excludes siblings, other drives, root and relative refs', () => {
  // Exercise the production function body without exporting or modifying production code.
  const body = source.match(/^  function collectRefs\(v\).*$/m)[0];
  const collect = new Function('path', 'assert', 'output', 'values', `const expectedOutputs={};${body};collectRefs(values);return expectedOutputs;`);
  const output = 'D:\\H\\output', hash = 'a'.repeat(64);
  const paths = ['D:\\H\\output\\package-0001.xlsx', 'D:/H/output/attempts/a.xlsx', 'D:\\H\\output-other\\a', 'D:\\H', 'E:\\H\\output\\a', output, 'package-0001.xlsx'];
  const result = collect(path.win32, assert, output, paths.map(p => ({path:p, sha256:hash})));
  assert.deepEqual(Object.keys(result), paths.slice(0, 2));
});
