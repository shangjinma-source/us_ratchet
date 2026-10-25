import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { SpreadsheetFile, Workbook } from "file:///C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const repo = "E:/Git/us_ratchet";
const evidenceDir = `${repo}/data/cache/research/ndx_dynamic_walkforward_v1`;
const outputDir = `${repo}/outputs/019f7db4-2df0-78a3-bbf0-1a896de09995`;
const outputXlsx = `${outputDir}/ndx_dynamic_portfolio_walkforward_report_v4.xlsx`;
const qaDir = `${outputDir}/ndx_dynamic_portfolio_walkforward_report_v4_qa`;

const files = {
  manifest: `${evidenceDir}/manifest.json`,
  summary: `${evidenceDir}/dynamic_policy_path_summary.csv`,
  artifactIndex: `${evidenceDir}/artifact_index.csv`,
  unavailable: `${evidenceDir}/unavailable_lanes.csv`,
  preferenceDiagnostics: `${evidenceDir}/user_preference_reference_diagnostics.csv`,
  preferenceCoverage: `${evidenceDir}/user_preference_reference_path_coverage.csv`,
  capitalSensitivityManifest: `${repo}/data/cache/research/ndx_cardinality_capital_sensitivity_v1/manifest.json`,
  capitalReplayManifest: `${repo}/data/cache/research/ndx_cardinality_capital_replay_v1/manifest.json`,
  capitalReplayJobs: `${repo}/data/cache/research/ndx_cardinality_capital_replay_v1/job_index.csv`,
  forwardV5Manifest: `${repo}/data/cache/research/ndx_challenger_forward_registry_v5/manifest.json`,
  forwardV5Registry: `${repo}/data/cache/research/ndx_challenger_forward_registry_v5/active_forward_registry.csv`,
  forwardV5Readiness: `${repo}/data/cache/research/ndx_challenger_forward_v5/readiness.json`,
  objectiveContract: `${repo}/config/ndx_portfolio_objective_v1.yaml`,
  selectorRegistry: `${repo}/config/ndx_dynamic_shadow_selector_registry_v1.yaml`,
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field.replace(/\r$/, ""));
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field !== "" || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const headers = (rows.shift() ?? []).map((header, index) => index === 0 ? header.replace(/^\uFEFF/, "") : header);
  return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, "utf8"));
}

async function readCsv(file) {
  return parseCsv(await fs.readFile(file, "utf8"));
}

async function sha256(file) {
  return createHash("sha256").update(await fs.readFile(file)).digest("hex");
}

function num(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function bool(value) {
  if (typeof value === "boolean") return value;
  if (value === "" || value === null || value === undefined) return null;
  return String(value).toLowerCase() === "true";
}

function json(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function shortBatch(value) {
  return String(value).replace("ndx_cardinality_real_runner_p2_", "");
}

function shortUniverse(value) {
  return value === "strict_technology" ? "严格科技" : value === "technology_plus_adjacent" ? "科技+邻接" : value;
}

function laneLabel(row) {
  return `${shortBatch(row.source_batch)}/${shortUniverse(row.universe_track)}/${row.policy_role}`;
}

function tickerShares(holdingsText) {
  const holdings = json(holdingsText, {});
  return Object.values(holdings)
    .map((item) => `${item.ticker}:${item.shares}`)
    .sort()
    .join("; ");
}

function tickerWeights(weightsText, holdingsText) {
  const weights = json(weightsText, {});
  const holdings = json(holdingsText, {});
  return Object.entries(weights)
    .map(([securityId, weight]) => `${holdings[securityId]?.ticker ?? securityId.split(":").slice(-1)[0]}:${(Number(weight) * 100).toFixed(2)}%`)
    .join("; ");
}

function listCount(value) {
  return json(value, []).length;
}

function colName(index) {
  let name = "";
  let n = index + 1;
  while (n > 0) {
    n -= 1;
    name = String.fromCharCode(65 + (n % 26)) + name;
    n = Math.floor(n / 26);
  }
  return name;
}

function writeMatrix(sheet, startRow, startCol, matrix) {
  if (!matrix.length || !matrix[0]?.length) return;
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, matrix[0].length).values = matrix;
}

const palette = {
  navy: "#15324B",
  teal: "#0F766E",
  blue: "#2563EB",
  paleBlue: "#EAF2F8",
  paleTeal: "#E7F5F3",
  paleGold: "#FFF4D6",
  paleRed: "#FDECEC",
  gray: "#64748B",
  lightGray: "#F3F6F8",
  border: "#D5DEE5",
  white: "#FFFFFF",
  green: "#137A4B",
  orange: "#C05A00",
};

function titleBand(sheet, range, title) {
  sheet.mergeCells(range);
  const cell = sheet.getRange(range);
  cell.values = [[title]];
  cell.format = { fill: palette.navy, font: { bold: true, color: palette.white, size: 18 }, verticalAlignment: "center" };
  cell.format.rowHeight = 34;
}

function sectionBand(sheet, range, text, fill = palette.teal) {
  sheet.mergeCells(range);
  const cell = sheet.getRange(range);
  cell.values = [[text]];
  cell.format = { fill, font: { bold: true, color: palette.white, size: 11 }, verticalAlignment: "center" };
  cell.format.rowHeight = 23;
}

function styleTable(sheet, range, headerRange) {
  sheet.getRange(range).format.borders = { preset: "all", style: "thin", color: palette.border };
  sheet.getRange(headerRange).format = {
    fill: palette.teal,
    font: { bold: true, color: palette.white },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(headerRange).format.rowHeight = 34;
}

function addTable(sheet, range, name) {
  const table = sheet.tables.add(range, true, name);
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRange(`${colName(index)}:${colName(index)}`).format.columnWidth = width;
  });
}

function pct(sheet, range) {
  sheet.getRange(range).format.numberFormat = "0.00%;[Red]-0.00%";
}

function drawdownCost(sheet, range) {
  sheet.getRange(range).format.numberFormat = "[Red]0.00%;[Green]-0.00%;0.00%";
}

function money(sheet, range) {
  sheet.getRange(range).format.numberFormat = "$#,##0.00;[Red]-$#,##0.00";
}

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(qaDir, { recursive: true });

const manifest = await readJson(files.manifest);
const capitalSensitivity = await readJson(files.capitalSensitivityManifest);
const capitalReplay = await readJson(files.capitalReplayManifest);
const forwardV5Manifest = await readJson(files.forwardV5Manifest);
const forwardReadiness = await readJson(files.forwardV5Readiness);
const summaryRows = await readCsv(files.summary);
const artifactIndex = await readCsv(files.artifactIndex);
const unavailableRows = await readCsv(files.unavailable);
const preferenceDiagnostics = await readCsv(files.preferenceDiagnostics);
const preferenceCoverage = await readCsv(files.preferenceCoverage);
const capitalJobs = await readCsv(files.capitalReplayJobs);
const forwardRows = await readCsv(files.forwardV5Registry);

const selectedRows = [];
const rebalanceRows = [];
const tradeRows = [];
for (const item of artifactIndex) {
  if (!item.path) continue;
  if (item.name === "selected_candidates") {
    for (const row of await readCsv(item.path)) selectedRows.push({ ...item, ...row });
  } else if (item.name === "whole_lot_rebalances") {
    for (const row of await readCsv(item.path)) rebalanceRows.push({ ...item, ...row });
  } else if (item.name === "whole_lot_trades") {
    for (const row of await readCsv(item.path)) tradeRows.push({ ...item, ...row });
  }
}

const wholeLotRows = summaryRows
  .filter((row) => row.execution_track === "whole_lot")
  .sort((a, b) => num(b.path_annualized_return_net) - num(a.path_annualized_return_net));
const competitiveWholeLotRows = wholeLotRows.filter((row) => row.policy_role !== "USER_PREFERENCE");
const preferenceWholeLotRows = wholeLotRows.filter((row) => row.policy_role === "USER_PREFERENCE");
const bestCompetitive = competitiveWholeLotRows[0];
const bestPreference = preferenceWholeLotRows[0];

const workbook = Workbook.create();
const overview = workbook.worksheets.add("结论");
const results = workbook.worksheets.add("路径结果");
const selections = workbook.worksheets.add("月度选择");
const rebalances = workbook.worksheets.add("整股再平衡");
const trades = workbook.worksheets.add("整股交易");
const capital = workbook.worksheets.add("资本重放");
const preference = workbook.worksheets.add("偏好诊断");
const audit = workbook.worksheets.add("审计检查");

// 路径结果
titleBand(results, "A1:AG1", "动态 k/组成/比例历史路径｜整股与分数股双轨");
results.mergeCells("A2:AG3");
results.getRange("A2:AG3").values = [["每条路径只在各自 source batch 内按预注册角色逐期选择；exact 与 bounded 语义不兼容且禁止合并。整股路径按决策后的首个共同交易日名义 Open 成交、Close 估值，继承 security_id、股数、现金与双边 10bp 成本。所有结果均为已消费历史，不是 fresh OOS 或实盘准入。"]];
results.getRange("A2:AG3").format = { fill: palette.paleGold, font: { color: palette.navy }, wrapText: true, verticalAlignment: "center" };
const resultHeaders = ["批次", "股票池", "角色", "执行轨", "路径起点", "估值截止", "交易日", "再平衡数", "k最小", "k最大", "k路径", "净收益", "年化收益", "最大回撤", "交易成本USD", "较原八只年化", "较原八只回撤成本", "较012922年化", "较012922回撤成本", "012922无未来", "三方同日", "目标路径日", "目标精确日", "目标滞后日", "精确覆盖率", "最大滞后天", "已登记新鲜度门", "新鲜度通过", "目标发布时间已知", "对齐用途", "允许准入", "fresh OOS", "允许晋级"];
const sortedSummary = [...summaryRows].sort((a, b) => {
  if (a.execution_track !== b.execution_track) return a.execution_track === "whole_lot" ? -1 : 1;
  return num(b.path_annualized_return_net) - num(a.path_annualized_return_net);
});
const resultData = sortedSummary.map((row) => [
  shortBatch(row.source_batch), shortUniverse(row.universe_track), row.policy_role, row.execution_track,
  row.path_start, row.valuation_end_date, num(row.trading_session_count), num(row.rebalance_count),
  num(row.minimum_target_k), num(row.maximum_target_k), row.k_path, num(row.path_return_net),
  num(row.path_annualized_return_net), num(row.path_max_drawdown), num(row.total_transaction_cost_usd),
  num(row.annualized_return_vs_original_8), num(row.max_drawdown_cost_vs_original_8),
  num(row.annualized_return_vs_012922), num(row.max_drawdown_cost_vs_012922), bool(row.target_asof_no_future_passed),
  bool(row.candidate_original_8_target_same_path_calendar),
  num(row.target_path_session_count), num(row.target_exact_source_date_count), num(row.target_lagged_session_count),
  num(row.target_exact_source_date_coverage_ratio), num(row.maximum_target_nav_lag_calendar_days),
  bool(row.target_nav_freshness_threshold_registered), bool(row.target_nav_freshness_passed),
  bool(row.target_publication_time_known), row.benchmark_alignment_role, bool(row.admission_allowed),
  bool(row.fresh_oos_consumed), bool(row.promotion_allowed),
]);
writeMatrix(results, 4, 0, [resultHeaders, ...resultData]);
styleTable(results, `A5:AG${5 + resultData.length}`, "A5:AG5");
addTable(results, `A5:AG${5 + resultData.length}`, "DynamicPathResults");
pct(results, `L6:N${5 + resultData.length}`);
money(results, `O6:O${5 + resultData.length}`);
pct(results, `P6:P${5 + resultData.length}`);
drawdownCost(results, `Q6:Q${5 + resultData.length}`);
pct(results, `R6:R${5 + resultData.length}`);
drawdownCost(results, `S6:S${5 + resultData.length}`);
pct(results, `Y6:Y${5 + resultData.length}`);
results.getRange(`K6:K${5 + resultData.length}`).format.wrapText = true;
results.freezePanes.freezeRows(5);
results.freezePanes.freezeColumns(4);
results.showGridLines = false;
setWidths(results, [16, 17, 19, 12, 13, 13, 10, 11, 9, 9, 34, 13, 14, 14, 16, 17, 20, 17, 20, 14, 14, 12, 12, 12, 14, 12, 16, 14, 17, 39, 13, 12, 13]);

// 月度选择
titleBand(selections, "A1:V1", "逐月选择｜动态持仓数、组成和权重真实竞争");
selections.mergeCells("A2:V3");
selections.getRange("A2:V3").values = [["同一 lane 的 ticker、k 和权重可以逐期改变。USER_PREFERENCE 固定为参照路径并保留旧约束失败原因；它不是候选池上限，也不获得准入豁免。"]];
selections.getRange("A2:V3").format = { fill: palette.paleBlue, font: { color: palette.navy }, wrapText: true, verticalAlignment: "center" };
const selectionHeaders = ["批次", "股票池", "角色", "选择日", "决策数据截止", "组合ID", "k", "股票", "权重规格", "权重", "收益P50", "收益P10", "回撤P50", "回撤P90", "较原八只收益P50", "较原八只收益P10", "较原八只回撤P50", "较原八只回撤P90", "换手", "旧约束通过", "失败原因", "训练选择"];
const selectionData = selectedRows
  .sort((a, b) => `${laneLabel(a)}|${a.selection_date}`.localeCompare(`${laneLabel(b)}|${b.selection_date}`))
  .map((row) => [
    shortBatch(row.source_batch), shortUniverse(row.universe_track), row.policy_role, row.selection_date,
    row.decision_data_end, row.portfolio_id, num(row.holding_count), row.tickers, row.weight_spec, row.weights,
    num(row.return_p50), num(row.return_p10), num(row.max_drawdown_p50), num(row.max_drawdown_p90),
    num(row.paired_return_p50_vs_incumbent), num(row.paired_return_p10_vs_incumbent),
    num(row.paired_drawdown_cost_p50_vs_incumbent), num(row.paired_drawdown_cost_p90_vs_incumbent),
    num(row.turnover), bool(row.declared_constraints_passed), row.constraint_failure_reasons, bool(row.training_selection_only),
  ]);
writeMatrix(selections, 4, 0, [selectionHeaders, ...selectionData]);
styleTable(selections, `A5:V${5 + selectionData.length}`, "A5:V5");
addTable(selections, `A5:V${5 + selectionData.length}`, "MonthlySelections");
pct(selections, `K6:P${5 + selectionData.length}`);
drawdownCost(selections, `Q6:R${5 + selectionData.length}`);
pct(selections, `S6:S${5 + selectionData.length}`);
selections.getRange(`H6:J${5 + selectionData.length}`).format.wrapText = true;
selections.getRange(`U6:U${5 + selectionData.length}`).format.wrapText = true;
selections.freezePanes.freezeRows(5);
selections.freezePanes.freezeColumns(4);
selections.showGridLines = false;
setWidths(selections, [15, 17, 19, 13, 15, 18, 8, 38, 30, 48, 13, 13, 13, 13, 18, 18, 20, 20, 13, 14, 45, 13]);

// 整股再平衡
titleBand(rebalances, "A1:W1", "逐期整股连续再平衡｜现金、股数与费用自融资继承");
rebalances.mergeCells("A2:W3");
rebalances.getRange("A2:W3").values = [["实际换股计买卖双边费用；同一 security_id 的 ticker 更名不视为经济交易。所有会计误差必须在收敛容差内，目标日必须早于执行日。"]];
rebalances.getRange("A2:W3").format = { fill: palette.paleGold, font: { color: palette.navy }, wrapText: true, verticalAlignment: "center" };
const rebalanceHeaders = ["批次", "股票池", "角色", "序号", "决策日", "执行日", "目标k", "交易前k", "交易后k", "新增数", "移除数", "延续数", "更名数", "目标权重", "执行后股数", "交易前现金", "交易后现金", "交易前权益", "交易后权益", "买入名义", "卖出名义", "费用", "会计误差"];
const rebalanceData = rebalanceRows
  .sort((a, b) => `${laneLabel(a)}|${String(a.rebalance_sequence).padStart(3, "0")}`.localeCompare(`${laneLabel(b)}|${String(b.rebalance_sequence).padStart(3, "0")}`))
  .map((row) => [
    shortBatch(row.source_batch), shortUniverse(row.universe_track), row.policy_role, num(row.rebalance_sequence),
    row.decision_date, row.execution_date, num(row.target_k), num(row.pretrade_k), num(row.posttrade_k),
    listCount(row.added_security_ids), listCount(row.removed_security_ids), listCount(row.continued_security_ids),
    listCount(row.renamed_security_ids), tickerWeights(row.target_weights, row.holdings), tickerShares(row.holdings),
    num(row.cash_before_usd), num(row.cash_after_usd), num(row.pretrade_equity_usd), num(row.posttrade_equity_usd),
    num(row.buy_notional_usd), num(row.sell_notional_usd), num(row.transaction_cost_usd), num(row.accounting_error_usd),
  ]);
writeMatrix(rebalances, 4, 0, [rebalanceHeaders, ...rebalanceData]);
styleTable(rebalances, `A5:W${5 + rebalanceData.length}`, "A5:W5");
addTable(rebalances, `A5:W${5 + rebalanceData.length}`, "WholeLotRebalances");
money(rebalances, `P6:V${5 + rebalanceData.length}`);
rebalances.getRange(`N6:O${5 + rebalanceData.length}`).format.wrapText = true;
rebalances.getRange(`W6:W${5 + rebalanceData.length}`).format.numberFormat = "0.000000000000";
rebalances.freezePanes.freezeRows(5);
rebalances.freezePanes.freezeColumns(6);
rebalances.showGridLines = false;
setWidths(rebalances, [15, 17, 19, 9, 13, 13, 10, 10, 10, 10, 10, 10, 10, 45, 45, 15, 15, 16, 16, 15, 15, 13, 18]);

// 整股交易
titleBand(trades, "A1:R1", "逐笔整股交易｜真实换股计成本，更名零交易");
const tradeHeaders = ["批次", "股票池", "角色", "再平衡序号", "决策日", "执行日", "事件", "动作", "交易ticker", "变更前ticker", "变更后ticker", "变更前股数", "变更后股数", "股数变化", "价格USD", "名义金额USD", "费用USD", "security_id"];
const tradeData = tradeRows
  .sort((a, b) => `${laneLabel(a)}|${String(a.rebalance_sequence).padStart(3, "0")}|${a.security_id}`.localeCompare(`${laneLabel(b)}|${String(b.rebalance_sequence).padStart(3, "0")}|${b.security_id}`))
  .map((row) => [
    shortBatch(row.source_batch), shortUniverse(row.universe_track), row.policy_role, num(row.rebalance_sequence),
    row.decision_date, row.execution_date, row.event_type, row.action, row.trade_ticker, row.before_ticker,
    row.after_ticker, num(row.shares_before), num(row.shares_after), num(row.share_delta), num(row.price_usd),
    num(row.notional_usd), num(row.transaction_cost_usd), row.security_id,
  ]);
writeMatrix(trades, 3, 0, [tradeHeaders, ...tradeData]);
styleTable(trades, `A4:R${4 + tradeData.length}`, "A4:R4");
addTable(trades, `A4:R${4 + tradeData.length}`, "WholeLotTrades");
money(trades, `O5:Q${4 + tradeData.length}`);
trades.freezePanes.freezeRows(4);
trades.freezePanes.freezeColumns(6);
trades.showGridLines = false;
setWidths(trades, [15, 17, 19, 11, 13, 13, 18, 10, 14, 14, 14, 12, 12, 12, 13, 16, 13, 33]);

// 资本重放
titleBand(capital, "A1:H1", "$25,000 完整股票袖套资本重放｜解除旧 $5,000 人工整股门");
writeMatrix(capital, 2, 0, [
  ["指标", "实际", "解释", "指标", "实际", "解释", "", ""],
  ["训练候选行", num(capitalSensitivity.counts.candidate_rows), "原始候选覆盖", "短名单", num(capitalSensitivity.counts.capital_replay_shortlist_rows), "六维 Pareto + 偏好参照", "", ""],
  ["旧资本USD", num(capitalSensitivity.source_training_cash_usd), "只作历史训练来源", "目标资本USD", num(capitalReplay.target_portfolio_cash_usd), "完整袖套比较资本", "", ""],
  ["整股专属失败", num(capitalSensitivity.counts.whole_lot_only_failed_rows), "$5k 造成的资本敏感性", "计划组", num(capitalReplay.planned_job_count), "批次×股票池×日期", "", ""],
  ["完成组", num(capitalReplay.completed), "必须等于计划组", "失败组", num(capitalReplay.failed), "必须为0", "", ""],
  ["持仓数范围", "4–21", "短名单观察范围，不是目标上限", "偏好参照行", num(capitalSensitivity.user_preference.shortlist_rows), "保留展示，不固定答案", "", ""],
]);
styleTable(capital, "A3:H8", "A3:H3");
money(capital, "B5:B5");
money(capital, "E5:E5");
sectionBand(capital, "A11:G11", "41 个完整重放作业组", palette.gray);
const jobHeaders = ["批次", "股票池", "选择日", "k范围", "短名单行", "状态", "输出目录"];
const jobData = capitalJobs.map((row) => [shortBatch(row.source_batch), shortUniverse(row.universe_track), row.selection_date, row.holding_counts, num(row.shortlist_rows), row.status, row.output_dir]);
writeMatrix(capital, 11, 0, [jobHeaders, ...jobData]);
styleTable(capital, `A12:G${12 + jobData.length}`, "A12:G12");
addTable(capital, `A12:G${12 + jobData.length}`, "CapitalReplayJobs");
capital.getRange(`D13:G${12 + jobData.length}`).format.wrapText = true;
capital.freezePanes.freezeRows(12);
capital.showGridLines = false;
setWidths(capital, [17, 18, 13, 34, 14, 22, 75]);

// 偏好诊断
titleBand(preference, "A1:M1", "USER_PREFERENCE：AMAT / AVGO / CDNS / GOOG｜参照，不是固定答案");
preference.mergeCells("A2:M3");
preference.getRange("A2:M3").values = [["来源日期完整保留；估值截止 2024-05-31 后的 2024-06-03 不执行。旧约束失败不会让偏好参照消失，也不会变成准入豁免。历史参照路径的强表现必须与 2026 年首个 21 日短 shadow 的落后证据并列理解。"]];
preference.getRange("A2:M3").format = { fill: palette.paleGold, font: { color: palette.navy }, wrapText: true, verticalAlignment: "center" };
const coverageHeaders = ["批次", "股票池", "参照角色", "来源坐标日", "来源参照日", "旧约束通过日", "实际执行日", "截止排除日", "失败不构成准入", "允许准入", "允许晋级"];
const coverageData = preferenceCoverage.map((row) => [shortBatch(row.source_batch), shortUniverse(row.universe_track), row.reference_role, num(row.source_coordinate_dates), num(row.source_reference_dates), num(row.source_declared_constraints_passed_dates), num(row.executed_reference_dates), row.cutoff_excluded_dates, bool(row.old_declared_constraint_failures_do_not_create_admission), bool(row.admission_allowed), bool(row.promotion_allowed)]);
writeMatrix(preference, 4, 0, [coverageHeaders, ...coverageData]);
styleTable(preference, `A5:K${5 + coverageData.length}`, "A5:K5");
addTable(preference, `A5:K${5 + coverageData.length}`, "PreferenceCoverage");
sectionBand(preference, "A11:M11", "逐日期来源约束诊断", palette.gray);
const diagHeaders = ["批次", "股票池", "选择日", "k", "股票", "权重规格", "旧约束通过", "失败原因", "整股可执行", "现金缓冲", "源结果角色", "偏好角色", "允许晋级"];
const diagData = preferenceDiagnostics.map((row) => [shortBatch(row.source_batch), shortUniverse(row.universe_track), row.selection_date, num(row.holding_count), row.tickers, row.weight_spec, bool(row.declared_constraints_passed), row.constraint_failure_reasons, bool(row.whole_lot_executable_all_windows), bool(row.whole_lot_cash_buffer_preserved), row.result_role, row.reference_role, bool(row.promotion_allowed)]);
writeMatrix(preference, 11, 0, [diagHeaders, ...diagData]);
styleTable(preference, `A12:M${12 + diagData.length}`, "A12:M12");
addTable(preference, `A12:M${12 + diagData.length}`, "PreferenceDiagnostics");
preference.getRange(`E13:H${12 + diagData.length}`).format.wrapText = true;
preference.freezePanes.freezeRows(12);
preference.showGridLines = false;
setWidths(preference, [16, 18, 13, 8, 31, 31, 14, 50, 16, 14, 27, 27, 14]);

// 审计检查
titleBand(audit, "A1:F1", "机器检查、来源与 SHA-256");
const checkRows = [
  ["检查", "实际", "期望", "状态", "说明", ""],
  ["历史路径行", summaryRows.length, 28, null, "14 lane × 整股/分数股", ""],
  ["不可用 lane", unavailableRows.length, 1, null, "bounded 无 USER_PREFERENCE 来源", ""],
  ["资本组完成", num(capitalReplay.completed), num(capitalReplay.planned_job_count), null, "完整 41 组", ""],
  ["资本组失败", num(capitalReplay.failed), 0, null, "必须为 0", ""],
  ["迁移控制混入", bool(manifest.migration_control_included), false, null, "主轨必须隔离", ""],
  ["动态 k/组成/比例", bool(manifest.dynamic_k_composition_and_weights_enabled), true, null, "不是固定名单", ""],
  ["Open/Close 分通道", bool(manifest.separate_execution_and_valuation_price_channels_required), true, null, "名义 Open 执行、Close 估值", ""],
  ["首个共同会话", bool(manifest.first_common_session_after_decision_required), true, null, "禁止同日/未来", ""],
  ["候选/原八只/012922同日", bool(manifest.candidate_original_8_target_same_path_calendar_required), true, null, "三方路径日严格相等", ""],
  ["原八只控制账持久化", bool(manifest.original_8_rebalance_trade_and_path_traces_persisted), true, null, "可外部重证", ""],
  ["012922 as-of账持久化", bool(manifest.target_012922_asof_trace_persisted), true, null, "逐日来源NAV和滞后", ""],
  ["批次合并", bool(manifest.cross_runner_results_merged), false, null, "exact/bounded 语义隔离", ""],
  ["fresh OOS", bool(manifest.fresh_oos_consumed), false, null, "历史仅作发现/反证", ""],
  ["允许晋级", bool(manifest.promotion_allowed), false, null, "正式门未满足", ""],
  ["保护哈希未变", bool(manifest.protected_hashes_unchanged), true, null, "config/state/broker", ""],
  ["实盘 config 写入", bool(manifest.live_mutation.config), false, null, "禁止", ""],
  ["state 写入", bool(manifest.live_mutation.state), false, null, "禁止", ""],
  ["今日建议写入", bool(manifest.live_mutation.today_advice), false, null, "禁止", ""],
  ["订单写入", bool(manifest.live_mutation.orders), false, null, "禁止", ""],
  ["v5 fresh cohort", num(forwardV5Manifest.fresh_oos_cohorts ?? 0), 0, null, "首个合法观察不早于 2026-10", ""],
  ["v5 promotion", bool(forwardV5Manifest.promotion_allowed), false, null, "正式 P4 等待", ""],
];
writeMatrix(audit, 2, 0, checkRows);
for (let row = 4; row <= 24; row += 1) audit.getRange(`D${row}`).formulas = [[`=IF(B${row}=C${row},"PASS","FAIL")`]];
styleTable(audit, "A3:F24", "A3:F3");
addTable(audit, "A3:F24", "AuditChecks");
audit.getRange("D4:D24").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#E7F6EC", font: { color: palette.green, bold: true } } });
audit.getRange("D4:D24").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: palette.paleRed, font: { color: "#B42318", bold: true } } });

sectionBand(audit, "A27:F27", "关键输入与内容哈希", palette.gray);
const sourceRows = [["键", "路径", "SHA-256", "类型", "用途", ""]];
for (const [key, file] of Object.entries(files)) {
  sourceRows.push([key, file, await sha256(file), path.extname(file).slice(1).toUpperCase(), "research evidence", ""]);
}
writeMatrix(audit, 27, 0, sourceRows);
styleTable(audit, `A28:F${27 + sourceRows.length}`, "A28:F28");
addTable(audit, `A28:F${27 + sourceRows.length}`, "SourceHashes");

const artifactStart = 31 + sourceRows.length;
sectionBand(audit, `A${artifactStart}:F${artifactStart}`, "动态路径派生产物索引", palette.gray);
const artifactRows = [["lane", "产物", "行数", "SHA-256", "路径", ""]];
for (const row of artifactIndex) artifactRows.push([laneLabel(row), row.name, num(row.rows), row.sha256, row.path, ""]);
writeMatrix(audit, artifactStart, 0, artifactRows);
styleTable(audit, `A${artifactStart + 1}:F${artifactStart + artifactRows.length}`, `A${artifactStart + 1}:F${artifactStart + 1}`);
addTable(audit, `A${artifactStart + 1}:F${artifactStart + artifactRows.length}`, "ArtifactHashes");
audit.getRange(`B29:E${artifactStart + artifactRows.length}`).format.wrapText = true;
audit.freezePanes.freezeRows(3);
audit.showGridLines = false;
setWidths(audit, [34, 88, 67, 12, 76, 8]);

// 结论页最后写，确保公式引用的源页已存在。
titleBand(overview, "A1:Q1", "NDX 动态组合历史 walk-forward｜本轮可交付结论");
overview.mergeCells("A2:Q3");
overview.getRange("A2:Q3").values = [["主轨是 VARIABLE_CARDINALITY portfolio_optimization：每期 k、security_id 组成和权重真实竞争。迁移控制、券商当前持仓和汇丰交易要求均不参与结构结论；012922 与原八只为双基准。历史结果用于发现和证伪，v5 future/OOS 独立晋级。"]];
overview.getRange("A2:Q3").format = { fill: palette.paleGold, font: { bold: true, color: palette.navy }, wrapText: true, verticalAlignment: "center" };

sectionBand(overview, "A5:H5", "关键数字");
writeMatrix(overview, 5, 0, [
  ["$25k重放作业", num(capitalReplay.completed), "历史路径", summaryRows.length, "整股路径", wholeLotRows.length, "fresh OOS", bool(manifest.fresh_oos_consumed) ? "是" : "否"],
  ["候选行", num(capitalSensitivity.counts.candidate_rows), "短名单", num(capitalSensitivity.counts.capital_replay_shortlist_rows), "短名单k范围", "4–21", "允许晋级", bool(manifest.promotion_allowed) ? "是" : "否"],
]);
overview.getRange("A6:H7").format = { fill: palette.lightGray, font: { bold: true, color: palette.navy }, borders: { preset: "all", style: "thin", color: palette.border } };

sectionBand(overview, "A9:H9", "结论与限制");
const conclusionRows = [
  ["动态结构已落地", "竞争路径整体覆盖 k=4–12；同一动态 lane 会跨期改变 k、股票和比例，股数、现金及费用连续。偏好参照固定 k=4 但不参与决定目标持仓数。", "工程 P1/P2 闭环"],
  ["竞争型低回撤代表", `${laneLabel(bestCompetitive)}：年化 ${(num(bestCompetitive.path_annualized_return_net) * 100).toFixed(2)}%，最大回撤 ${(num(bestCompetitive.path_max_drawdown) * 100).toFixed(2)}%；较原八只年化 ${(num(bestCompetitive.annualized_return_vs_original_8) * 100).toFixed(2)}pct。`, "真实取舍，不晋级"],
  ["用户偏好参照", `AMAT/AVGO/CDNS/GOOG 整股历史年化 ${(num(bestPreference.path_annualized_return_net) * 100).toFixed(2)}%、回撤 ${(num(bestPreference.path_max_drawdown) * 100).toFixed(2)}%；但旧约束多期失败，且 2026 年短 shadow 曾显著落后，因此只保留参照。`, "不是固定答案"],
  ["双基准", "每条路径同时报告相对原八只与 012922 的年化收益和回撤成本；目标基金 23/293 日采用 as-of 滞后，最大 8 天，未注册新鲜度阈值，不能冒充 admission。", "componentwise"],
  ["$25k 修正", "$5,000 训练整股门曾人为排除高价/高 k 结构；本轮 41/41 作业已在 $25,000、$100 buffer、10bp 下完整重放。", "旧结果未被当最终答案"],
  ["前瞻边界", `v5 当前状态 ${forwardReadiness.status ?? "WAITING"}；首个合法 fresh observation 不早于 2026-10，正式门仍为 12 个成熟 126 日 cohort、2 类 regime。`, "P4 未完成"],
  ["实盘隔离", "config/state/今日建议/订单均未自动修改；当前结果不会生成挂单或卖出建议。", "promotion=false"],
];
writeMatrix(overview, 9, 0, [["主题", "发现", "解释"], ...conclusionRows]);
styleTable(overview, "A10:H17", "A10:H10");
for (let row = 11; row <= 17; row += 1) {
  overview.mergeCells(`B${row}:G${row}`);
  overview.getRange(`B${row}:G${row}`).format.wrapText = true;
}
overview.getRange("A11:A17").format = { fill: palette.paleTeal, font: { bold: true, color: palette.teal }, borders: { preset: "all", style: "thin", color: palette.border }, wrapText: true };
overview.getRange("H11:H17").format = { fill: palette.lightGray, font: { italic: true, color: palette.gray }, borders: { preset: "all", style: "thin", color: palette.border }, wrapText: true };
overview.getRange("A11:H17").format.rowHeight = 45;

sectionBand(overview, "A20:H20", "竞争型整股路径（按历史年化排序，偏好参照另列）");
const topCompetitive = competitiveWholeLotRows.slice(0, 8);
const topHeaders = ["lane", "年化收益", "最大回撤", "较原八只年化", "较原八只回撤", "较012922年化", "较012922回撤", "k范围"];
const topData = topCompetitive.map((row) => [laneLabel(row), num(row.path_annualized_return_net), num(row.path_max_drawdown), num(row.annualized_return_vs_original_8), num(row.max_drawdown_cost_vs_original_8), num(row.annualized_return_vs_012922), num(row.max_drawdown_cost_vs_012922), `${row.minimum_target_k}–${row.maximum_target_k}`]);
writeMatrix(overview, 20, 0, [topHeaders, ...topData]);
styleTable(overview, `A21:H${21 + topData.length}`, "A21:H21");
pct(overview, `B22:D${21 + topData.length}`);
drawdownCost(overview, `E22:E${21 + topData.length}`);
pct(overview, `F22:F${21 + topData.length}`);
drawdownCost(overview, `G22:G${21 + topData.length}`);
overview.getRange(`A22:A${21 + topData.length}`).format.wrapText = true;

// 公式驱动的图表辅助区域。
writeMatrix(overview, 4, 9, [["lane", "年化收益", "最大回撤"]]);
for (let i = 0; i < topData.length; i += 1) {
  const sourceRow = 22 + i;
  const helperRow = 6 + i;
  overview.getRange(`J${helperRow}`).formulas = [[`=A${sourceRow}`]];
  overview.getRange(`K${helperRow}`).formulas = [[`=B${sourceRow}`]];
  overview.getRange(`L${helperRow}`).formulas = [[`=C${sourceRow}`]];
}
pct(overview, `K6:L${5 + topData.length}`);
const chart = overview.charts.add("bar", overview.getRange(`J5:L${5 + topData.length}`));
chart.setPosition("J15", "Q31");
chart.title = "竞争型整股路径：历史年化收益与最大回撤";
chart.titleTextStyle.fontSize = 12;
chart.hasLegend = true;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
chart.yAxis = { numberFormatCode: "0%" };

sectionBand(overview, "A32:H32", "交付检查");
writeMatrix(overview, 32, 0, [["检查", "状态", "检查", "状态", "检查", "状态", "检查", "状态"]]);
overview.getRange("A34").values = [["资本重放"]];
overview.getRange("B34").formulas = [["='审计检查'!D6"]];
overview.getRange("C34").values = [["动态路径"]];
overview.getRange("D34").formulas = [["='审计检查'!D4"]];
overview.getRange("E34").values = [["实盘隔离"]];
overview.getRange("F34").formulas = [["=IF(AND('审计检查'!D19=\"PASS\",'审计检查'!D20=\"PASS\",'审计检查'!D21=\"PASS\",'审计检查'!D22=\"PASS\"),\"PASS\",\"FAIL\")"]];
overview.getRange("G34").values = [["晋级关闭"]];
overview.getRange("H34").formulas = [["='审计检查'!D17"]];
overview.getRange("A33:H34").format.borders = { preset: "all", style: "thin", color: palette.border };
overview.getRange("A33:H33").format = { fill: palette.lightGray, font: { bold: true, color: palette.navy }, borders: { preset: "all", style: "thin", color: palette.border } };
overview.getRange("B34,D34,F34,H34").format = { fill: "#E7F6EC", font: { bold: true, color: palette.green }, horizontalAlignment: "center" };
overview.mergeCells("A37:H39");
overview.getRange("A37:H39").values = [["阅读顺序：先看“结论”理解边界，再到“路径结果”比较双基准；用“月度选择”确认 k/组成/权重逐期变化；用“整股再平衡/整股交易”复核现金与费用；最后查看“资本重放、偏好诊断、审计检查”。"]];
overview.getRange("A37:H39").format = { fill: palette.paleBlue, font: { color: palette.navy }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: palette.border } };
overview.freezePanes.freezeRows(5);
overview.showGridLines = false;
setWidths(overview, [22, 16, 17, 16, 18, 16, 18, 17, 3, 28, 14, 14, 3, 12, 12, 12, 12]);

const workbookInspect = await workbook.inspect({ kind: "workbook,sheet,table,chart", maxChars: 14000, tableMaxRows: 5, tableMaxCols: 10, tableMaxCellChars: 100 });
await fs.writeFile(`${qaDir}/workbook_inspect.json`, JSON.stringify(workbookInspect, null, 2), "utf8");
const formulaErrors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "formula error scan" });
await fs.writeFile(`${qaDir}/formula_errors.json`, JSON.stringify(formulaErrors, null, 2), "utf8");

const previews = [
  ["结论", "A1:Q39", "01_结论.png"],
  ["路径结果", `A1:AG${Math.min(5 + resultData.length, 34)}`, "02_路径结果.png"],
  ["月度选择", `A1:V${Math.min(5 + selectionData.length, 35)}`, "03_月度选择.png"],
  ["整股再平衡", `A1:W${Math.min(5 + rebalanceData.length, 32)}`, "04_整股再平衡.png"],
  ["整股交易", `A1:R${Math.min(4 + tradeData.length, 34)}`, "05_整股交易.png"],
  ["资本重放", "A1:H30", "06_资本重放.png"],
  ["偏好诊断", `A1:M${Math.min(12 + diagData.length, 34)}`, "07_偏好诊断.png"],
  ["审计检查", `A1:F${Math.min(artifactStart + artifactRows.length, 55)}`, "08_审计检查.png"],
];
for (const [sheetName, range, fileName] of previews) {
  const rendered = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${qaDir}/${fileName}`, new Uint8Array(await rendered.arrayBuffer()));
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputXlsx);
console.log(JSON.stringify({
  outputXlsx,
  manifestSha256: await sha256(files.manifest),
  summaryRows: summaryRows.length,
  selectedRows: selectedRows.length,
  rebalanceRows: rebalanceRows.length,
  tradeRows: tradeRows.length,
  artifactRows: artifactIndex.length,
  unavailableRows: unavailableRows.length,
  previews: previews.length,
}, null, 2));
