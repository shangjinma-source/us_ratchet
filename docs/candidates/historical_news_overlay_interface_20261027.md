# 历史新闻事件叠加：现有引擎复用核查

只读核查，未新增回测。**历史规则可以回测；“只能前瞻”过于绝对。**当代模型对过去事件的判断可能带记忆泄漏，历史结果须标条件性，不能因此放弃所有可重复的历史经济检验，也不能把它当独立样本外证明。

## 可复用账户与真实输入

| 项目 | 早窗 | 后窗 |
|---|---|---|
| 目录（仓库相对） | tmp/recent_continuous_baseline_20261026_v7 | tmp/old_continuous_baseline_20261026_v9 |
| 初始决策—终值 | 2020-12-31—2023-12-29 | 2023-12-29—2026-07-30 |
| 首执行 | 2021-01-04 | 2024-01-02 |
| 月度决策数 | 36 | 31 |
| 各月 prices 域 / 全窗并集 | 100–102 / 122 SID | 100–101 / 127 SID |

每目录实际包含 `execution_inputs.json`、`book.json`、`independent_prefix_review.json`、`generic_complete_report_v1.json`。`book.json.daily_ledger` 为逐日资金/股份/权益；`order_log` 为成交；`provider_audit` 为每日目标/风险/订单证据；`selection_account_states` 为月度实际账户输入。证券身份用各月 `assembled.monthly_inputs[*].search_arguments` 的 prices/metadata、原 provenance 及日期身份映射，不按今天 ticker 生硬拼接。两个账户独立，不串接。

## 最小执行接口

复用 `backtest.historical_dividend_frontier_research.run_frontier_capped_next_open(assembled, ohlc, initial_cash, fee_bps, slippage_bps, risk, progress, verified_prefix, max_new_searches, dividend_events)`；固定初始 20000、fee0、slip5、原 8192 搜索预算与 seed。冻结现有文件，新建隔离研究 wrapper。

最小**卖出/禁买至预设解除时点**规则可封装 risk adapter：`apply(*, day, month, target, closes, adjustments=()) -> (effective_target, diagnostics)`；先正常调用 `MonthlyExitCoreResearchAdapter.apply` 保留原20%退出，再对明确命中事件 SID 将数量置0，其余不变；原 wrapper 已检查相同 SID 集合和 `0 <= quantity <= ceiling`，自动生成次开盘订单。保留/代理 base.state，兼容 WAIT_POST_ACTION_MARK 审查；该特殊分支不得强行发单。事件禁止状态独立保存，不能月末意外丢失。

该接口不含实际账户股份，**不能直接实现“只暂停新增买入但不卖已有仓”**；那种规则需新增接收 provider callback `arguments['state']` 的叠加点及独立订单复核。首次只选一个清楚规则，不把不同语义混在一个实验内。规则的事件类别、触发阈值、持续/解除条件须在看经济结果前冻结，本核查不预先宣布任何类别值得卖出。

有事件后账户路径改变，后续月选股必须按实际分支账户重算；不能复制基准后续选择。可复用 `scripts/run_long_market_trend_probe_v1.py` 的有界子进程、exact-argument checkpoint、逐月 exposure gate 结构，但不能调用其 QQQ 规则或改原冻结文件。公司行动仍按当前分支实际暴露审查，缺口阻塞。独立 reviewer 必须新增事件触发/解除及订单验证，原 reviewer 不懂新 overlay；资金/股息/股份算术可复用。完整通过后才用通用完整账户报告器，禁止前缀年化。

## 一次固定规则仍缺的输入

1. 选定历史事件集合及覆盖清单：具体 SID/日期、已检查但无事件与无法取得的区别；不得只挑基准亏损交易。若先限定财报子域，应明确仅该子域事件叠加，其余继承基准，不宣称全新闻覆盖。
2. 可审计原始公告/财报文本、原版本与 URL/hash、历史公开时间及证据、报告期、日期身份映射。今天下载时间单独保存，不能伪造当时采集；无法核实原版本/时点的事件排除或独立敏感性报告。
3. 冻结事件抽取 schema、模型/提示版本、原文证据定位、标签、规则和成本预算。模型只抽取原文事实，禁止用之后行情作输入；历史记忆风险单列。可确定性提取的数字/日期先用代码核验，并用人工少量核对发现事实错误。
4. `available_at` 与交易日 cutoff：保守在已证实公开之后的决策收盘使用，次开盘成交；盘后公告不得赶回当天收盘。只有日期无时区时采用预先声明的保守延迟，而非结果导向选择。
5. 事件输入 manifest/source pins 与新分支选择、目标、成交、权益账本、独立审查。上限沿用每窗最多36/31新搜索、每次最多3600秒、无自动重试；公司行动新增缺口保留检查点，不解除门槛。

采用要求仍为保持或提高年化、降低最大回撤；同时看交易成本、错失上涨和恢复时间。固定规则历史比较可用于淘汰无效机制；通过也需揭示非PIT、模型记忆与来源缺失，不自动视为上线充分证据。不调多组阈值追求达标。
