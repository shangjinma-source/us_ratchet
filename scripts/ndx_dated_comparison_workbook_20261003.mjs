/** Workbook construction from an externally verified Chinese display payload.
 * No file I/O or economic calculations. The publishing caller must bind input
 * bytes, render all sheets, inspect the exported file and publish its manifest.
 */
import assert from 'node:assert/strict';

const names = ['研究概览', '全部任务', '四轨指标', '双基准距离', '原始目标权重', '来源索引'];
const widths = [[40, 105], [10, 72, 15, 30, 24], [12, 24, 36, 22, 24, 18, 18, 18], [12, 27, 20, 20, 20, 22, 22, 26], [12, 72, 16, 28, 28, 20], [20, 100, 72]];
const trackLabels = ['候选整数账户', '原组合整数账户', '候选连续权重', '原组合连续权重'];
const modeLabels = ['严格同日汇率', '向前取最近有效汇率'];

export function literal(value) {
  // Artifact Tool treats an initial equals sign as a formula unless escaped.
  return typeof value === 'string' && value.startsWith('=') ? `'${value}` : value;
}

export function exactTextFormat(value) {
  if (typeof value !== 'string') return null;
  const exact = /^[0-9a-fA-F]{64}$/.test(value) || (/^[0-9]+$/.test(value) && (value.length > 15 || (value.length > 1 && value.startsWith('0'))));
  if (!exact) return '@';
  assert(value.length <= 64, 'Exact text literal exceeds bounded format length');
  return `"${value}"`;
}

export function validateDisplay(payload) {
  assert.equal(payload.schema, 'SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1');
  for (const flag of ['formal_comparison_passed', 'future_independent_oos', 'promotion_allowed', 'point_in_time_verified', 'economics_recomputed', 'workbook_created']) assert.equal(payload[flag], false, flag);
  const display = payload.display;
  assert.equal(display.schema, 'DATED_COMPARISON_CHINESE_DISPLAY_TABLES_V1');
  for (const flag of ['source_bytes_authenticated', 'economics_recomputed', 'formal_comparison_passed', 'future_independent_oos']) assert.equal(display[flag], false, flag);
  assert.deepEqual(display.tables.map(table => table.name), names);
  for (const table of display.tables) {
    assert(Array.isArray(table.headers) && table.headers.length === widths[names.indexOf(table.name)].length);
    assert(table.headers.every(header => typeof header === 'string'));
    assert(Array.isArray(table.rows));
    assert(Array.isArray(table.percentage_columns));
    for (const column of table.percentage_columns) assert(Number.isInteger(column) && column >= 0 && column < table.headers.length);
    for (const row of table.rows) {
      assert.equal(row.length, table.headers.length);
      for (const value of row) {
        assert(value === null || ['string', 'number', 'boolean'].includes(typeof value));
        if (typeof value === 'number') assert(Number.isFinite(value) && (!Number.isInteger(value) || Number.isSafeInteger(value)), 'Unsafe display number');
      }
    }
  }
  const [, tasks, metrics, distances, weights, sources] = display.tables;
  assert.deepEqual(display.tables[0].rows.slice(0, 5), [
    ['固定队列任务数', 1632], ['已有独审比较', 1632], ['未提供比较', 0],
    ['完整组合域任务数（精确文本）', '6222659648236112670'],
    ['完整域未在本比较汇总中体现（精确文本）', '6222659648236111038'],
  ], 'Exact complete-domain overview');
  assert.equal(tasks.rows.length, 1632);
  assert.equal(new Set(tasks.rows.map(row => row[1])).size, 1632);
  tasks.rows.forEach((row, index) => {
    assert.equal(row[0], index + 1);
    assert(Number.isInteger(row[2]) && row[2] >= 4 && row[2] <= 20);
    assert.equal(row[4], '已有独审比较');
  });
  assert.equal(metrics.rows.length, 1632 * 4);
  metrics.rows.forEach((row, index) => {
    assert.equal(row[0], Math.floor(index / 4) + 1);
    assert.equal(row[1], trackLabels[index % 4]);
    assert(row.slice(5).every(value => value === null || typeof value === 'number'));
  });
  assert.equal(distances.rows.length, 1632 * 8);
  distances.rows.forEach((row, index) => {
    assert.equal(row[0], Math.floor(index / 8) + 1);
    assert.equal(row[1], modeLabels[Math.floor(index % 8 / 4)]);
    assert.equal(row[2], index % 4 < 2 ? '整数账户' : '连续权重');
    assert.equal(row[3], index % 2 === 0 ? '年化收益' : '最大回撤');
    assert(row.slice(4).every(value => value === null || typeof value === 'number'));
  });
  const counts = Array(1632).fill(0);
  for (const row of weights.rows) {
    assert(Number.isInteger(row[0]) && row[0] >= 1 && row[0] <= 1632);
    assert.equal(row[1], tasks.rows[row[0] - 1][1]);
    assert(typeof row[5] === 'number' && row[5] >= 0);
    counts[row[0] - 1] += 1;
  }
  assert.deepEqual(counts, tasks.rows.map(row => row[2]));
  assert.deepEqual(sources.rows.map(row => row[0]), ['summary', 'publication', 'audit', 'reader', 'adapter']);
  for (const row of sources.rows) assert.deepEqual(row.slice(1), [payload.input_references[row[0]].path, payload.input_references[row[0]].sha256]);
  return display.tables;
}

export function buildWorkbook(Workbook, payload) {
  const tables = validateDisplay(payload);
  const workbook = Workbook.create();
  const renderRegions = [];
  tables.forEach((table, index) => {
    const sheet = workbook.worksheets.add(table.name);
    sheet.showGridLines = false;
    const height = table.rows.length + 4;
    const columns = table.headers.length;
    const fullRange = sheet.getRangeByIndexes(0, 0, height, columns);
    fullRange.format.font = { name: 'Microsoft YaHei', size: 11, color: '#172B40' };
    fullRange.format.rowHeight = 25;
    fullRange.format.verticalAlignment = 'center';
    sheet.getRange('A1').values = [[table.name === '研究概览' ? 'Nasdaq-100 条件历史研究' : table.name]];
    sheet.getRange('A1').format.font = { name: 'Microsoft YaHei', size: 16, bold: true, color: '#123B56' };
    sheet.getRange('A2').values = [['2026-03-20 至 2026-09-21｜单路径诊断；不授正式晋级或未来 OOS']];
    const header = sheet.getRangeByIndexes(3, 0, 1, columns);
    header.values = [table.headers.map(literal)];
    header.format.fill = '#123B56';
    header.format.font = { name: 'Microsoft YaHei', size: 11, bold: true, color: '#FFFFFF' };
    header.format.rowHeight = 36;
    header.format.wrapText = true;
    // General formatting may display numeric-looking strings as rounded numbers.
    // Keep identifiers and exact domain counts visibly textual as well as typed.
    if (index === 0) sheet.getRange('B8:B9').setNumberFormat('@');
    if (index === 1) sheet.getRangeByIndexes(4, 1, table.rows.length, 1).setNumberFormat('@');
    if (index === 4) sheet.getRangeByIndexes(4, 1, table.rows.length, 4).setNumberFormat('@');
    if (index === 5) sheet.getRangeByIndexes(4, 0, table.rows.length, 3).setNumberFormat('@');
    if (table.rows.length) sheet.getRangeByIndexes(4, 0, table.rows.length, columns).values = table.rows.map(row => row.map(literal));
    widths[index].forEach((width, column) => { sheet.getRangeByIndexes(0, column, height, 1).format.columnWidth = width; });
    for (const column of table.percentage_columns) {
      if (table.rows.length) sheet.getRangeByIndexes(4, column, table.rows.length, 1).setNumberFormat('0.0%;(0.0%);0.0%');
    }
    // Apply textual display only; never replace the original cell value.
    table.rows.forEach((row, rowIndex) => row.forEach((value, column) => {
      const format = exactTextFormat(value);
      if (format !== null) sheet.getRangeByIndexes(rowIndex + 4, column, 1, 1).setNumberFormat(format);
    }));
    if (index === 0) {
      sheet.getRangeByIndexes(4, 0, table.rows.length, columns).format.wrapText = true;
      sheet.getRangeByIndexes(4, 0, table.rows.length, columns).format.rowHeight = 42;
    } else {
      sheet.tables.add(`A4:${String.fromCharCode(64 + columns)}${height}`, true, `ResearchTable${index}`);
      sheet.freezePanes.freezeRows(4);
      sheet.freezePanes.freezeColumns(1);
    }
    renderRegions.push({ sheetName: table.name, range: `A1:${String.fromCharCode(64 + columns)}${Math.min(height, 18)}`, finalRow: height });
  });
  workbook.recalculate();
  return { workbook, renderRegions, sourceBytesAuthenticatedByBuilder: false, exportVerified: false };
}
