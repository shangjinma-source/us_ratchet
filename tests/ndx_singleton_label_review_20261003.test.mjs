import assert from 'node:assert/strict';
import {test} from 'node:test';
import {repairSingletonPathLabel, originalSingletonLabelFormula} from '../scripts/ndx_dated_singleton_path_label_repair_20261003.mjs';

function fixture(correct = true) {
  const id = 'f'.repeat(64), accesses = [], writes = [];
  const cells = {B4: {values: [[1]]}, B5: {values: [['#VALUE!']]}};
  let formula = [[originalSingletonLabelFormula]];
  Object.defineProperty(cells.B5, 'formulas', {get: () => formula, set: v => {writes.push('B5'); formula = v;}});
  const workbook = {worksheets: {getItem: sheet => ({getRange: cell => {
    accesses.push(`${sheet}!${cell}`);
    if (sheet === '任务索引' && cell === 'B2') return {values: [[`ID: ${id}`]]};
    assert.equal(sheet, '路径查看'); assert.ok(cell in cells); return cells[cell];
  }})}, recalculate: () => {if (correct) cells.B5.values = [[`ID: ${id}`]];}};
  return {id, workbook, cells, accesses, writes};
}

test('only exact B5 assigned; no chart data or risk cells accessed', () => {
  const f = fixture(); const r = repairSingletonPathLabel(f.workbook, [f.id]);
  assert.deepEqual(f.writes, ['B5']);
  assert.deepEqual(new Set(f.accesses), new Set(['任务索引!B2', '路径查看!B4', '路径查看!B5']));
  for (const key of ['source_bytes_authenticated', 'full_workbook_verified', 'visual_acceptance_passed', 'workbook_delivered']) assert.equal(r[key], false);
});

test('failed recalculation cannot return success; typed selector guards reject before mutation', () => {
  const failed = fixture(false); assert.throws(() => repairSingletonPathLabel(failed.workbook, [failed.id]), /Recalculated source label/);
  for (const value of ['1', true, null, 0, 2, 1.5]) {
    const f = fixture(); f.cells.B4.values = [[value]];
    assert.throws(() => repairSingletonPathLabel(f.workbook, [f.id]));
    assert.deepEqual(f.writes, []);
  }
});
