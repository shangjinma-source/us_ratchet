import test from 'node:test';
import assert from 'node:assert/strict';
import { literal, validateDisplay } from '../scripts/ndx_dated_comparison_workbook_20261003.mjs';

export function fixture() {
  const taskRows = [], metricRows = [], distanceRows = [], weightRows = [];
  for (let ordinal = 1; ordinal <= 1632; ordinal += 1) {
    const identifier = ordinal.toString(16).padStart(64, '0');
    taskRows.push([ordinal, identifier, 4, '等权', '已有独审比较']);
    for (const track of ['候选整数账户', '原组合整数账户', '候选连续权重', '原组合连续权重']) metricRows.push([ordinal, track, '已有路径', '不适用', '无执行记录', 0, 0, 0]);
    for (const mode of ['严格同日汇率', '向前取最近有效汇率']) for (const kind of ['整数账户', '连续权重']) for (const metric of ['年化收益', '最大回撤']) distanceRows.push([ordinal, mode, kind, metric, 0, 0, 0, 0]);
    for (let position = 0; position < 4; position += 1) weightRows.push([ordinal, identifier, `T${position}`, `SID${position}`, `ISSUER${position}`, position === 0 ? 0 : 0.4]);
  }
  const references = Object.fromEntries(['summary', 'publication', 'audit', 'reader', 'adapter'].map(role => [role, { path: role, sha256: 'a'.repeat(64) }]));
  const make = (name, count, rows, percentages = []) => ({ name, headers: Array.from({ length: count }, (_, index) => `列${index}`), rows, percentage_columns: percentages });
  const overview = [['固定队列任务数', 1632], ['已有独审比较', 1632], ['未提供比较', 0], ['完整组合域任务数（精确文本）', '6222659648236112670'], ['完整域未在本比较汇总中体现（精确文本）', '6222659648236111038']];
  const tables = [make('研究概览', 2, overview), make('全部任务', 5, taskRows), make('四轨指标', 8, metricRows, [5, 6, 7]), make('双基准距离', 8, distanceRows, [4, 5, 6, 7]), make('原始目标权重', 6, weightRows, [5]), make('来源索引', 3, Object.entries(references).map(([role, ref]) => [role, ref.path, ref.sha256]))];
  return { schema: 'SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1', formal_comparison_passed: false, future_independent_oos: false, promotion_allowed: false, point_in_time_verified: false, economics_recomputed: false, workbook_created: false, input_references: references, display: { schema: 'DATED_COMPARISON_CHINESE_DISPLAY_TABLES_V1', source_bytes_authenticated: false, economics_recomputed: false, formal_comparison_passed: false, future_independent_oos: false, tables } };
}

test('full display preserves zero, absence, signed distances and unnormalized weights', () => {
  const payload = fixture();
  payload.display.tables[2].rows[0].splice(5, 3, null, null, null);
  payload.display.tables[3].rows[0][7] = -0.25;
  const before = JSON.stringify(payload);
  const result = validateDisplay(payload);
  assert.equal(JSON.stringify(payload), before);
  assert.equal(result[2].rows[0][5], null);
  assert.equal(result[2].rows[1][5], 0);
  assert.equal(result[3].rows[0][7], -0.25);
  assert.equal(result[4].rows[0][5], 0);
  assert.equal(result[4].rows[1][5], 0.4);
});

test('reject collapsed domain, unsafe numeric cells, missing mode and false-like authority', () => {
  for (const mutate of [
    payload => payload.display.tables[1].rows.pop(),
    payload => { payload.display.tables[1].rows[1][1] = payload.display.tables[1].rows[0][1]; },
    payload => payload.display.tables[3].rows.pop(),
    payload => { payload.display.tables[3].rows[4][1] = '严格同日汇率'; },
    payload => { payload.display.tables[0].rows[0][1] = 6222659648236112670; },
    payload => { payload.display.tables[0].rows[3][1] = '6222659648236112000'; },
    payload => { payload.future_independent_oos = 0; },
    payload => { payload.display.tables[5].rows[0][2] = 'b'.repeat(64); },
  ]) {
    const payload = fixture();
    mutate(payload);
    assert.throws(() => validateDisplay(payload));
  }
});

test('literal source labels cannot become formulas and null stays null', () => {
  assert.equal(literal('=HYPERLINK("example")'), '\'=HYPERLINK("example")');
  assert.equal(literal(null), null);
  assert.equal(literal(0), 0);
  assert.equal(literal('普通文本'), '普通文本');
});
