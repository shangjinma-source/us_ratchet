/** Native path-chart component. No IO, source authentication, or research selection. */
import assert from 'node:assert/strict';

const roles = ['candidate_integer', 'incumbent_integer', 'candidate_continuous', 'incumbent_continuous', 'STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX'];
const labels = ['候选整数账户', '原组合整数账户', '候选连续权重', '原组合连续权重', '012922严格同日汇率', '012922最近有效汇率'];
const sharedRoles = [roles[1], roles[3], roles[4], roles[5]];
const font = 'Microsoft YaHei';
const literal = value => typeof value === 'string' && value.startsWith('=') ? `'${value}` : value;
const numeric = slot => slot.display_value === null ? '缺失或超出展示精度' : slot.display_value;

// Match Python Fraction -> binary64 display conversion, including subnormal ties.
// This checks a saved display scalar; it does not recalculate economic values.
function savedRatio(value) {
  if (typeof value === 'number') { assert(Number.isFinite(value)); value = String(value); }
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    assert.deepEqual(Object.keys(value).sort(), ['denominator', 'numerator']);
    assert.equal(typeof value.numerator, 'string'); assert.equal(typeof value.denominator, 'string');
    assert.match(value.numerator, /^[+-]?\d+$/); assert.match(value.denominator, /^\d+$/);
    assert(value.numerator.length <= 10000 && value.denominator.length <= 10000);
    const n = BigInt(value.numerator), d = BigInt(value.denominator); assert(d > 0n); return [n, d];
  }
  assert.equal(typeof value, 'string'); assert(value.length > 0 && value.length <= 10000);
  if (/^[+-]?\d+\/\d+$/.test(value)) {
    const [n, d] = value.split('/').map(BigInt); assert(d > 0n); return [n, d];
  }
  const parts = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(value);
  assert(parts, 'Saved finite rational or decimal');
  const fraction = parts[3] ?? parts[4] ?? '', exponent = Number(parts[5] ?? 0) - fraction.length;
  assert(Number.isSafeInteger(exponent) && Math.abs(exponent) <= 10000);
  const n = BigInt((parts[2] ?? '') + fraction) * (parts[1] === '-' ? -1n : 1n);
  return exponent >= 0 ? [n * 10n ** BigInt(exponent), 1n] : [n, 10n ** BigInt(-exponent)];
}
function binaryDisplay(value) {
  let [n, d] = savedRatio(value); if (n === 0n) return 0;
  const sign = n < 0n ? -1 : 1; if (n < 0n) n = -n;
  let e = n.toString(2).length - d.toString(2).length;
  if (e >= 0 ? n < (d << BigInt(e)) : (n << BigInt(-e)) < d) e--;
  if (e > 1023) return sign * Infinity;
  if (e < -1075) return sign * 0;
  const scale = e < -1022 ? 1074 : 52 - e;
  const numerator = scale >= 0 ? n << BigInt(scale) : n;
  const denominator = scale >= 0 ? d : d << BigInt(-scale);
  let q = numerator / denominator; const remainder = numerator % denominator;
  if (2n * remainder > denominator || (2n * remainder === denominator && q % 2n === 1n)) q++;
  return sign * Number(q) * 2 ** (-scale);
}
function validateSlot(slot) {
  if (slot.exact_value === null) {
    assert.equal(slot.display_value, null); assert.equal(slot.display_status, 'MISSING_SAVED_VALUE'); return;
  }
  const [n] = savedRatio(slot.exact_value), expected = binaryDisplay(slot.exact_value);
  if (!Number.isFinite(expected) || (expected === 0 && n !== 0n)) {
    assert.equal(slot.display_value, null); assert.equal(slot.display_status, 'OUTSIDE_DISPLAY_PRECISION');
  } else {
    assert.equal(typeof slot.display_value, 'number'); assert.equal(slot.display_value, expected);
    assert.equal(slot.display_status, 'FINITE_BINARY_FLOAT_DISPLAY');
  }
}
function validateReference(ref) {
  assert(ref && typeof ref === 'object' && !Array.isArray(ref));
  assert.deepEqual(Object.keys(ref).sort(), ['json_pointer', 'path', 'sha256']);
  assert.equal(typeof ref.path, 'string'); assert(ref.path.length > 0 && ref.path.trim() === ref.path);
  assert.match(ref.sha256, /^[a-f0-9]{64}$/); assert.equal(typeof ref.json_pointer, 'string'); assert(ref.json_pointer.startsWith('/'));
}

export function validatePathTasks(tasks, expectedTaskIds) {
  assert(Array.isArray(tasks) && tasks.length > 0); assert(Array.isArray(expectedTaskIds));
  assert.deepEqual(tasks.map(task => task.numerical_task_id), expectedTaskIds);
  assert.equal(new Set(expectedTaskIds).size, tasks.length);
  const calendar = tasks[0].calendar;
  assert.equal(calendar.length, 127);
  assert.deepEqual(calendar, [...new Set(calendar)].sort());
  assert.equal(calendar[0], '2026-03-20'); assert.equal(calendar[1], '2026-03-23');
  for (const day of calendar) {
    assert.equal(typeof day, 'string'); assert.match(day, /^\d{4}-\d{2}-\d{2}$/);
    const parsed = new Date(`${day}T00:00:00Z`); assert.equal(parsed.toISOString().slice(0, 10), day);
    assert(parsed.getUTCDay() > 0 && parsed.getUTCDay() < 6);
  }
  assert.equal(calendar[126], '2026-09-21');
  for (const task of tasks) {
    assert.equal(task.schema, 'DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1');
    assert.match(task.numerical_task_id, /^[0-9a-f]{64}$/);
    assert.equal(task.original_task_summary_row.numerical_task_id, task.numerical_task_id);
    assert.deepEqual(task.calendar, calendar);
    assert.equal(task.evaluation_interval_previously_used_for_fitting, true);
    for (const key of ['source_bytes_authenticated', 'formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed', 'future_independent_oos', 'economics_recomputed', 'risk_recomputed', 'risk_chains_reaggregated', 'account_executed', 'winner_selected']) assert.equal(task[key], false);
    assert.deepEqual(Object.keys(task.series).sort(), [...roles].sort());
    const references = new Map();
    assert.deepEqual(Object.keys(task.source_index).sort(), roles.filter(role => task.series[role].source_reference !== null).sort());
    for (const role of roles) {
      const series = task.series[role];
      assert.equal(series.slots.length, 127);
      assert.deepEqual(series.slots.map(slot => slot.session), calendar);
      assert.equal(series.transformation, 'COPY_SAVED_NORMALIZED_VALUES_NO_RETURN_RECALCULATION');
      const missing = ['NOT_EXECUTED_NONPOSITIVE_TARGET', 'TECHNICAL_MISSING'].includes(series.status);
      if (missing) {
        assert.equal(role, 'candidate_integer'); assert.equal(series.source_reference, null);
        assert(!Object.hasOwn(task.source_index, role)); assert(series.missing_evidence !== null && series.missing_evidence !== undefined);
        for (const slot of series.slots) assert.equal(slot.exact_value, null);
      } else {
        assert.equal(series.status, roles.slice(4).includes(role) ? 'SAVED_NAV_REFERENCE' : 'AVAILABLE');
        validateReference(series.source_reference); assert.deepEqual(series.source_reference, task.source_index[role]);
        const ref = series.source_reference; assert(!references.has(ref.path) || references.get(ref.path) === ref.sha256); references.set(ref.path, ref.sha256);
      }
      for (const slot of series.slots) validateSlot(slot);
      if (sharedRoles.includes(role)) assert.deepEqual(series, tasks[0].series[role]);
    }
  }
  return calendar;
}

function table(sheet, headers, rows, widths) {
  const height = rows.length + 1;
  sheet.showGridLines = false;
  const range = sheet.getRangeByIndexes(0, 0, height, headers.length);
  range.format.font = { name: font, size: 11, color: '#172B40' };
  range.format.rowHeight = 24;
  sheet.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
  sheet.getRangeByIndexes(0, 0, 1, headers.length).format.fill = '#123B56';
  sheet.getRangeByIndexes(0, 0, 1, headers.length).format.font = { name: font, size: 11, color: '#FFFFFF', bold: true };
  if (rows.length) sheet.getRangeByIndexes(1, 0, rows.length, headers.length).values = rows.map(row => row.map(literal));
  widths.forEach((width, index) => { sheet.getRangeByIndexes(0, index, height, 1).format.columnWidth = width; });
  sheet.freezePanes.freezeRows(1);
}

export function buildPathComparisonWorkbook(Workbook, tasks, expectedTaskIds) {
  const calendar = validatePathTasks(tasks, expectedTaskIds);
  const workbook = Workbook.create();
  const view = workbook.worksheets.add('路径查看');
  const index = workbook.worksheets.add('任务索引');
  const candidate = workbook.worksheets.add('候选路径');
  const shared = workbook.worksheets.add('共享路径');
  const indexRows = tasks.map((task, i) => [i + 1, `ID: ${task.numerical_task_id}`, task.original_task_summary_row.k,
    JSON.stringify(task.original_task_summary_row.weight_spec), task.series.candidate_integer.status, task.numerical_task_id]);
  table(index, ['本包序号', '完整任务ID显示', '证券数', '原权重规格', '整数路径状态', '原始ID文本'], indexRows, [14, 82, 12, 40, 42, 76]);
  index.getRange(`F2:F${tasks.length + 1}`).setNumberFormat('@');
  const candidateRows = [];
  for (const task of tasks) for (let i = 0; i < 127; i++) {
    const left = task.series.candidate_integer.slots[i], right = task.series.candidate_continuous.slots[i];
    candidateRows.push([calendar[i], numeric(left), numeric(right), JSON.stringify(left.exact_value), JSON.stringify(right.exact_value), left.display_status, right.display_status]);
  }
  table(candidate, ['日期', labels[0], labels[2], '整数原精确值', '连续原精确值', '整数显示状态', '连续显示状态'], candidateRows, [16, 22, 22, 38, 38, 36, 36]);
  const sharedRows = calendar.map((day, i) => [day, ...sharedRoles.map(role => numeric(tasks[0].series[role].slots[i])), ...sharedRoles.map(role => JSON.stringify(tasks[0].series[role].slots[i].exact_value))]);
  table(shared, ['日期', labels[1], labels[3], labels[4], labels[5], '原8整数精确值', '原8连续精确值', '严格汇率精确值', '最近汇率精确值'], sharedRows, [16, 22, 22, 26, 26, 38, 38, 38, 38]);
  view.showGridLines = false;
  const used = view.getRange('A1:G175');
  used.format.font = { name: font, size: 11, color: '#172B40' };
  used.format.rowHeight = 24;
  [17, 22, 22, 22, 22, 25, 25].forEach((width, col) => { view.getRangeByIndexes(0, col, 175, 1).format.columnWidth = width; });
  view.getRange('A2').values = [['同期路径比较']];
  view.getRange('A2').format.font = { name: font, size: 16, bold: true, color: '#123B56' };
  view.getRange('A4').values = [['本包任务序号']];
  view.getRange('B4').values = [[1]];
  view.getRange('B4').format.fill = '#FFF2CC';
  view.dataValidations.add({ range: 'B4', rule: { type: 'whole', operator: 'between', formula1: 1, formula2: tasks.length } });
  view.getRange('A5').values = [['当前任务ID']];
  const selected = expression => `IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=${tasks.length}),${expression},NA()),NA())`;
  view.getRange('B5').formulas = [[`=${selected(`INDEX('任务索引'!$B$2:$B$${tasks.length + 1},$B$4)`)}`]];
  view.getRange('A7').values = [['历史条件诊断；评价窗已被先前拟合使用，非独立OOS。图中缺口表示未提供或超出显示精度。']];
  view.getRange('A48:G48').values = [['日期', ...labels]];
  const helper = calendar.map((day, i) => {
    const candidateIndex = `($B$4-1)*127+${i + 1}`;
    const references = [`INDEX('候选路径'!$B$2:$B$${candidateRows.length + 1},${candidateIndex})`, `'共享路径'!B${i + 2}`,
      `INDEX('候选路径'!$C$2:$C$${candidateRows.length + 1},${candidateIndex})`, `'共享路径'!C${i + 2}`, `'共享路径'!D${i + 2}`, `'共享路径'!E${i + 2}`];
    return [`='共享路径'!A${i + 2}`, ...references.map(ref => `=${selected(`IF(ISNUMBER(${ref}),${ref},NA())`)}`)];
  });
  view.getRange('A49:G175').formulas = helper;
  view.getRange('B49:G175').setNumberFormat('0.000');
  const charts = [];
  for (const [title, columns, start, end] of [
    ['整数账户与012922（期初=1）', ['A', 'B', 'C', 'F', 'G'], 'A9', 'G26'],
    ['连续权重与012922（期初=1）', ['A', 'D', 'E', 'F', 'G'], 'A28', 'G45'],
  ]) {
    const chart = view.charts.add('line', columns.map(column => view.getRange(`${column}48:${column}175`)));
    chart.title = title;
    chart.titleTextStyle.typeface = font;
    chart.titleTextStyle.fontSize = 15;
    chart.legend = { position: 'top', textStyle: { typeface: font, fontSize: 11 } };
    chart.xAxis = { axisType: 'textAxis', tickLabelInterval: 21, textStyle: { typeface: font, fontSize: 10 } };
    chart.yAxis = { numberFormatCode: '0.0', numberFormatSourceLinked: false, textStyle: { typeface: font, fontSize: 10 } };
    chart.setPosition(start, end);
    ['#245C84', '#A76531', '#667684', '#A1AAB0'].forEach((color, i) => { chart.series.items[i].line = { fill: color, style: i > 1 ? 'dashed' : 'solid', width: 2 }; });
    charts.push({ title, categoryRange: '路径查看!A49:A175', series: chart.series.items.map(series => ({ formula: series.formula, categoryFormula: series.categoryFormula })) });
  }
  workbook.recalculate();
  return { workbook, charts, taskIds: [...expectedTaskIds], defaultTaskId: expectedTaskIds[0],
    componentScope: 'PATH_CHARTS_ONLY_NOT_COMPLETE_H_WORKBOOK', sourceBytesAuthenticated: false,
    exportedWorkbookVerified: false, missingChartMarker: 'DELIBERATE_NA_ERROR_GAP_NEVER_ZERO' };
}
