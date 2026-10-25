/** Full navigation and classification display. No IO or source authentication. */
import assert from 'node:assert/strict';

const flags = ['source_bytes_authenticated', 'formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed', 'future_independent_oos', 'economics_recomputed', 'risk_recomputed', 'risk_chains_reaggregated', 'account_executed', 'winner_selected'];
const indexFlags = ['source_bytes_authenticated', 'formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed', 'future_independent_oos', 'account_executed', 'fit_performed', 'economic_metrics_recomputed', 'risk_reaggregated', 'workbook_delivered', 'charts_rendered', 'visual_acceptance_passed', 'xlsx_actual_size_limit_verified', 'full_transitive_source_closure_reverified'];
const text = value => typeof value === 'string' && value.startsWith('=') ? `'${value}` : value;
const json = value => JSON.stringify(value);
const safeInteger = value => assert(Number.isSafeInteger(value) && value >= 0);
function reference(value) {
  assert(value && typeof value === 'object');
  assert.equal(typeof value.path, 'string'); assert(value.path.length > 0);
  assert.match(value.sha256, /^[0-9a-f]{64}$/);
}

export function validateNavigation(index, classification, packages, expectedTaskIds) {
  assert.equal(index.schema, 'SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1');
  assert.equal(classification.schema, 'DATED_WORKBOOK_CLASSIFICATION_TABLE_V1');
  for (const flag of indexFlags) assert.equal(index[flag], false);
  for (const flag of flags) assert.equal(classification[flag], false);
  assert.equal(index.planned_task_count, 1632);
  assert.equal(expectedTaskIds.length, 1632); assert.equal(new Set(expectedTaskIds).size, 1632);
  assert.deepEqual(index.task_index.map(row => row.numerical_task_id), expectedTaskIds);
  const mapped = new Map(); const names = new Set(); let ordinal = 0;
  for (const [packageIndex, bundle] of packages.entries()) {
    assert.equal(bundle.package_index, packageIndex);
    assert.match(bundle.filename, /^package-[0-9]{4}\.xlsx$/); assert(!names.has(bundle.filename)); names.add(bundle.filename);
    assert.equal(bundle.start_task_ordinal, ordinal);
    safeInteger(bundle.stop_task_ordinal); assert(bundle.stop_task_ordinal > ordinal);
    assert.equal(bundle.tasks.length, bundle.stop_task_ordinal - ordinal);
    for (const [local, row] of bundle.tasks.entries()) {
      assert.equal(row.task_ordinal, ordinal); assert.equal(row.numerical_task_id, expectedTaskIds[ordinal]);
      assert.equal(row.local_task_number, local + 1);
      for (const key of ['comparison_status', 'integer_status', 'continuous_status']) assert.equal(typeof row[key], 'string');
      assert.equal(row.navigation_row, local + 2);
      mapped.set(row.numerical_task_id, { ...row, filename: bundle.filename }); ordinal++;
    }
    assert.equal(bundle.stop_task_ordinal, ordinal);
  }
  assert.equal(ordinal, 1632);
  for (const [i, row] of index.task_index.entries()) {
    assert.equal(row.task_ordinal, i); assert.match(row.numerical_task_id, /^[0-9a-f]{64}$/);
    assert.equal(mapped.get(row.numerical_task_id).comparison_status, row.status);
    safeInteger(row.k); assert(row.k >= 4 && row.k <= 20);
    assert(typeof row.weight_spec === 'string' && row.weight_spec.length > 0 || row.weight_spec && typeof row.weight_spec === 'object' && !Array.isArray(row.weight_spec));
  }
  assert.equal(classification.rows.length, 101);
  assert.equal(new Set(classification.rows.map(row => row.ticker)).size, 101);
  const selected = classification.rows.filter(row => row.training_selected);
  const known = classification.rows.filter(row => row.conditional_label_present);
  assert.equal(known.length, 78); assert.equal(selected.length, 77);
  assert.equal(new Set(selected.map(row => row.security_id)).size, 77);
  assert.equal(new Set(selected.map(row => row.issuer_id)).size, 76);
  for (const [key, value] of Object.entries({ observed_security_rows: 101, conditional_labeled_security_count: 78, unknown_label_rows: 23, training_selected_security_count: 77, training_selected_issuer_count: 76, formally_verified_rows: 0 })) assert.equal(classification.counts[key], value);
  for (const row of classification.rows) {
    assert.equal(typeof row.ticker, 'string'); assert(row.ticker.length > 0);
    assert.equal(typeof row.training_selected, 'boolean'); assert.equal(typeof row.conditional_label_present, 'boolean');
    assert.equal(row.formally_verified, false);
    assert(row.saved_risk_chain === null || typeof row.saved_risk_chain === 'string');
    assert.equal(row.conditional_label_present, row.saved_risk_chain !== null && row.saved_risk_chain !== 'unclassified');
    if (row.training_selected) {
      assert(row.conditional_label_present); assert.equal(typeof row.security_id, 'string'); assert.equal(typeof row.issuer_id, 'string');
    }
    reference(row.wiring_row_reference); reference(row.training_provenance_reference);
    assert(row.wiring_row_reference.json_pointer.startsWith('/')); assert(row.training_provenance_reference.json_pointer.startsWith('/'));
  }
  reference(index.classification_reference); reference(index.task_jsonl_reference);
  return mapped;
}

function table(workbook, name, headings, rows, widths, tableName) {
  const sheet = workbook.worksheets.add(name); sheet.showGridLines = false;
  const range = sheet.getRangeByIndexes(0, 0, rows.length + 1, headings.length);
  range.format.font = { name: 'Microsoft YaHei', size: 11, color: '#172B40' }; range.format.rowHeight = 26;
  sheet.getRangeByIndexes(0, 0, 1, headings.length).values = [headings];
  if (rows.length) sheet.getRangeByIndexes(1, 0, rows.length, headings.length).values = rows.map(row => row.map(value => {
    assert(value === null || ['string', 'number', 'boolean'].includes(typeof value));
    assert(typeof value !== 'number' || Number.isFinite(value) && (!Number.isInteger(value) || Number.isSafeInteger(value)), 'Unsafe numeric input must remain source text');
    const literal = text(value);
    assert(typeof literal !== 'string' || literal.length <= 32767, 'Excel cell limit; keep full evidence in linked JSON'); return literal;
  }));
  widths.forEach((width, col) => { sheet.getRangeByIndexes(0, col, rows.length + 1, 1).format.columnWidth = width; });
  const header = sheet.getRangeByIndexes(0, 0, 1, headings.length);
  header.format.fill = '#123B56'; header.format.font = { name: 'Microsoft YaHei', size: 11, color: '#FFFFFF', bold: true };
  let column = headings.length, last = '';
  while (column > 0) { column--; last = String.fromCharCode(65 + column % 26) + last; column = Math.floor(column / 26); }
  sheet.freezePanes.freezeRows(1); sheet.tables.add(`A1:${last}${rows.length + 1}`, true, tableName);
  return sheet;
}

export function buildExtensionNavigationWorkbook(Workbook, index, classification, packages, expectedTaskIds) {
  const mapped = validateNavigation(index, classification, packages, expectedTaskIds);
  const workbook = Workbook.create(); const intro = workbook.worksheets.add('使用说明');
  intro.showGridLines = false; intro.getRange('A1:H15').format.font = { name: 'Microsoft YaHei', size: 12, color: '#172B40' };
  intro.getRange('A1:H15').format.columnWidth = 18; intro.getRange('A1:H15').format.rowHeight = 28;
  intro.getRange('A2').values = [['路径与风险导航']]; intro.getRange('A2').format.font = { name: 'Microsoft YaHei', size: 18, bold: true, color: '#123B56' };
  intro.getRange('A4').values = [['在全部任务中打开对应数据包，再选择本包序号查看曲线和风险。默认显示原序首项、首日。']];
  intro.getRange('A6:B11').values = [['任务数', 1632], ['分类来源证券', 101], ['条件标签证券', 78], ['未知标签证券', 23], ['训练证券／发行人', '77 / 76'], ['正式分类认证', 0]];
  intro.getRange('A13').values = [['历史条件研究：评价窗已被先前拟合使用，不属于独立OOS。缺失值与真实现金账户分别保留。']];
  const rows = index.task_index.map(row => {
    const position = mapped.get(row.numerical_task_id);
    return [row.task_ordinal + 1, `ID: ${row.numerical_task_id}`, row.k, json(row.weight_spec), row.status,
      position.integer_status, position.continuous_status, position.filename, position.local_task_number,
      `分类/来源与风险时点待认证；非独立OOS`, json(row.jsonl_record), row.numerical_task_id];
  });
  const nav = table(workbook, '全部任务', ['原序号', '任务ID显示', '证券数', '原权重规格', '比较状态', '整数路径状态', '连续路径状态', '打开数据包', '本包序号', '未晋级原因', '完整显示数据定位', '原ID文本'], rows, [12, 82, 12, 72, 35, 42, 35, 28, 12, 58, 65, 76], 'AllExtensionTasks');
  nav.getRange('L2:L1633').setNumberFormat('@');
  // Artifact Tool's HYPERLINK evaluator returns an unimplemented message. Keep
  // readable values and return native OOXML link intents for the export adapter.
  const nativeHyperlinks = index.task_index.map(row => {
    const p = mapped.get(row.numerical_task_id);
    return { worksheet: '全部任务', cell: `H${row.task_ordinal + 2}`, target: p.filename, location: `'任务索引'!A${p.navigation_row}` };
  });
  const classRows = classification.rows.map((row, i) => [i + 1, row.ticker, row.security_id, row.issuer_id, row.saved_risk_chain ?? '未知', row.training_selected ? '是' : '否', row.classification_status,
    json(row.nonselection_evidence), json(row.original_wiring_row.original_windows), json(row.original_wiring_row.new_assumed_window), '未认证', `classification.json#/rows/${i}`, json(row.wiring_row_reference), json(row.training_provenance_reference)]);
  table(workbook, '分类覆盖', ['原序号', '证券代码', '证券身份', '发行人身份', '保存条件标签', '训练入选', '分类状态', '原非入选证据', '原窗口', '新假设窗口', '正式认证', '完整来源及限制', '风险接线来源', '训练来源'], classRows, [12, 14, 48, 30, 26, 14, 38, 70, 55, 55, 16, 42, 80, 80], 'ClassificationCoverage');
  table(workbook, '数据来源', ['用途', '路径', 'SHA256', '说明'], [
    ['显示JSONL', index.task_jsonl_reference.path, `SHA256: ${index.task_jsonl_reference.sha256}`, '全部任务路径、风险、原精确值与来源'],
    ['分类完整数据', index.classification_reference.path, `SHA256: ${index.classification_reference.sha256}`, '101行原来源、风险来源时点、原窗口及限制完整保留'],
  ], [24, 100, 100, 90], 'ExtensionSources');
  workbook.recalculate();
  return { workbook, nativeHyperlinks, hyperlinksApplied: false, taskIds: [...expectedTaskIds], taskCount: 1632, classificationCount: 101, defaultTaskId: expectedTaskIds[0], sourceBytesAuthenticated: false, exportedWorkbookVerified: false };
}
