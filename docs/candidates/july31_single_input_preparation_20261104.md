# 7月31日单次输入：已完成条件性编译

2026-11-04 实际调用原纯函数 compile_monthly_training_window 成功。原 101 只价格域各有 253 个收盘，日期为 2025-07-30 至 2026-07-31；输出 101 个证券成本和 12 个非重叠 21 日训练场景。SPCX、HONA 因真实交易历史不足 253 日排除。没有运行选股搜索或资金账本，不能称为新回测收益、完整历史成员认证或样本外验证。

复现：`D:/python/python.exe scripts/research/prepare_july31_single_input_20261104.py`。本地输出 `tmp/july31_single_input_20261104/coordinate_review.json` 保存条件、来源 hash 和复核时间；`single_window_draft.json` 保存逐证券审查与全部输入 hash；`single_window_input.json` 是原编译器实际输出。状态 COMPILED_CONDITIONAL，search_calls=0、book_calls=0。原始行情仅留本地。

## 日历和已有资产复用

复用 `tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json` 的最后 6/30 窗口身份及原 training_source；逐一复算原名义成本，与旧成本在既有表达误差阈值内一致。原训练信号规则不变：HON、CMCSA、WDC、ILMN 保留既有供应商分拆调整训练价格，不把全部训练统一改成名义报价；HON 沿既有 6/29 后 SID。

日历引用 `tmp/old_window_official_calendar_20261026/review.json` 绑定的全年官方节假日证据并逐 hash 验证：7/31 非休市日，AAPL 原始响应有当日 bar，253 个参考交易日均有行情。保留临时停市档案非穷尽限制。生产 daily_calendar_2026_extension 实际从 9/22 开始，未用它证明 7 月日历；早期“随意追加且完全待认证”的草稿说明已由本核验取代。

## CRWD：股数事件与价格坐标已条件性核对

[6/3 SEC 8-K](https://www.sec.gov/Archives/edgar/data/1535527/000153552726000022/crwd-20260603.htm) 在决策日前公告四拆一，7/2 开始拆后交易，与原供应商事件的 7/2、比例 4 精确一致。[8/26 公告](https://www.sec.gov/Archives/edgar/data/1535527/000153552726000029/crwd-20260826xex991.htm) 只作事后完成核对，其财报信息没有进入训练。官方原始请求返回 403，保存的是 web 工具解析观察，不是官方原始 HTML。

来源和请求记录在 crwd_sources/。输入保留原供应商拆股调整训练；名义成本仅恢复决策日之后的拆股因子，因此不会把已生效的四拆一再次乘回 7/31 成本。CRWD 原 6/30 成本重放差为 0，7/31 收盘与名义成本均约 190.86000061 美元。代码只接受这项精确日期与比例，新出现其他事件仍拒绝。

## EA：仅追加 7/31，保留跨源限制

原 CSV 的 2,895 个已有值逐值检查完全不变；15 个原来缺失的 7 月日期复用原冻结 `tmp/old_continuous_baseline_20261026_v9/execution_inputs.json` 同 SID OHLC，再仅追加 7/31。新价格来自保存的 [ChartExchange](https://chartexchange.com/symbol/nasdaq-ea/historical/) 原始 HTML，代码重新解析表格并验证原文件 hash；7/31 OHLC 与保存的 [StockAnalysis](https://stockanalysis.com/stocks/ea/history/) 页面观察精确一致。第二来源是工具读取表格观察，不是原始 HTML。7/31 收盘 209.86 美元。

新旧来源 367 个重叠日期中有 8 个历史 1 美分差异，全部保留在记录；没有改写成一致，没有用容差覆盖旧值。条件性接受依据仅为同一已审查 SID、同一美元价格尺度及新增日两来源 OHLC 一致；这是显式研究数据拼接假设，不是交易所原始成交认证。原 candidate 的 BLOCKED_PRICE_OVERLAP 文件不改写，由独立 review 限定追加范围。

## 剩余边界

原 101 域仍是条件性沿用，不能证明到 7/31 所有旧成员均未被移除；SPCX/HONA 短史排除不能补足此事实。供应商没有记录行动不等于全量官方无行动证明。当前仅完成真实可编译输入，尚未搜索、未补完整 8 月执行事件、未处理 EA 并购现金账务，未改变生产策略或账户。下一步先固定上述研究范围，再考虑一次有限单月验证，不重跑已否决趋势组合或扩展参数。
