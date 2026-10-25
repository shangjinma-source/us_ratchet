/** Narrow in-memory repair for a new export version; never opens saved files. */
import assert from 'node:assert/strict';

const selected = expression => `=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),${expression},NA()),NA())`;
export const originalSingletonLabelFormula = selected("INDEX('任务索引'!$B$2:$B$2,$B$4)");
export const repairedSingletonLabelFormula = selected("'任务索引'!$B$2");

export function repairSingletonPathLabel(workbook, expectedTaskIds) {
  assert(Array.isArray(expectedTaskIds) && expectedTaskIds.length === 1, 'Exactly one original task');
  const id = expectedTaskIds[0];
  assert.match(id, /^[0-9a-f]{64}$/);
  const view = workbook.worksheets.getItem('路径查看');
  const index = workbook.worksheets.getItem('任务索引');
  assert.equal(index.getRange('B2').values[0][0], `ID: ${id}`, 'Exact saved label');
  assert.equal(view.getRange('B4').values[0][0], 1, 'Default selector before repair');
  assert.equal(view.getRange('B5').formulas[0][0], originalSingletonLabelFormula, 'Only known frozen formula');
  view.getRange('B5').formulas = [[repairedSingletonLabelFormula]];
  workbook.recalculate();
  assert.equal(view.getRange('B5').values[0][0], `ID: ${id}`, 'Recalculated source label');
  return {schema: 'DATED_SINGLETON_PATH_LABEL_REPAIR_V1', task_id: id,
    worksheet: '路径查看', cell: 'B5', previous_formula: originalSingletonLabelFormula,
    formula: repairedSingletonLabelFormula, selector_validation_preserved: true,
    saved_source_files_modified: false, economic_values_recomputed: false,
    source_bytes_authenticated: false, full_workbook_verified: false,
    visual_acceptance_passed: false, workbook_delivered: false};
}
