# 风险预算：实际V27月度目标64日库存（纠正后）

**撤回旧59/67及raw目标清单：旧版误用限仓后重排前raw_selection，它不代表V27最终目标。本版改为原book.provider_audit首次该月monthly_ceiling，绑定book哈希、audit索引及rerank_decision_id。旧59/67不可用于覆盖判断。**

纠正后补证前：56/67个月条件组件可用，11个月有具体缺项。限定补证后：67个月已编译同口径63日含息风险输入；仅条件性输入准备完成，未运行风险策略或账户收益回测，不是PIT认证。

| 决策日 | 实际monthly_ceiling股票 | 补证前缺项 |
|---|---|---|
|2020-12-31|MRNA,TSLA|条件组件可复用|
|2021-01-29|MRNA,TSLA,ZM|条件组件可复用|
|2021-02-26|MRNA,TSLA|条件组件可复用|
|2021-03-31|ALXN,CHTR,PDD,PTON|ALXN / SOURCE_EVENT_STREAM_NOT_JSON_CHART:JSONDecodeError|
|2021-04-30|MRNA,TSLA|条件组件可复用|
|2021-05-28|MRNA,TSLA|条件组件可复用|
|2021-06-30|MRNA,TSLA|条件组件可复用|
|2021-07-30|MRNA|条件组件可复用|
|2021-08-31|MRNA|条件组件可复用|
|2021-09-30|MRNA|条件组件可复用|
|2021-10-29|MRNA|条件组件可复用|
|2021-11-30|MRNA,NVDA|条件组件可复用|
|2021-12-31|FTNT,LCID|条件组件可复用|
|2022-01-31|FTNT,NVDA|条件组件可复用|
|2022-02-28|FTNT|条件组件可复用|
|2022-03-31|NVDA,PANW|NVDA / UNMAPPED_LOOKBACK_DIVIDEND:2022-03-02|
|2022-04-29|PANW|条件组件可复用|
|2022-05-31|DLTR|条件组件可复用|
|2022-06-30|DLTR|条件组件可复用|
|2022-07-29|DLTR|条件组件可复用|
|2022-08-31|DLTR,VRTX|条件组件可复用|
|2022-09-30|VRTX|条件组件可复用|
|2022-10-31|VRTX|条件组件可复用|
|2022-11-30|ENPH,VRTX|条件组件可复用|
|2022-12-30|ENPH,PDD|条件组件可复用|
|2023-01-31|ENPH,PDD|条件组件可复用|
|2023-02-28|CEG,PDD|CEG / UNMAPPED_LOOKBACK_DIVIDEND:2023-02-24|
|2023-03-31|PDD,SGEN|SGEN / SOURCE_EVENT_STREAM_NOT_JSON_CHART:JSONDecodeError|
|2023-04-28|NFLX,PDD|条件组件可复用|
|2023-05-31|NFLX,NVDA|NVDA / UNMAPPED_LOOKBACK_DIVIDEND:2023-03-07|
|2023-06-30|NFLX,NVDA|条件组件可复用|
|2023-07-31|CHTR,NVDA,PDD|条件组件可复用|
|2023-08-31|CHTR,NVDA|条件组件可复用|
|2023-09-29|CHTR,NVDA|条件组件可复用|
|2023-10-31|META,NVDA|条件组件可复用|
|2023-11-30|META,NVDA|条件组件可复用|
|2023-12-29|TSLA,GOOG|条件组件可复用|
|2024-01-31|NVDA|条件组件可复用|
|2024-02-29|NVDA|条件组件可复用|
|2024-03-28|NVDA|条件组件可复用|
|2024-04-30|NVDA|条件组件可复用|
|2024-05-31|ABNB,PDD|条件组件可复用|
|2024-06-28|NVDA|NVDA / UNMAPPED_LOOKBACK_DIVIDEND:2024-06-11|
|2024-07-31|NVDA,SMCI|NVDA / UNMAPPED_LOOKBACK_DIVIDEND:2024-06-11|
|2024-08-30|NVDA,SMCI|NVDA / UNMAPPED_LOOKBACK_DIVIDEND:2024-06-11|
|2024-09-30|NVDA,ARM|条件组件可复用|
|2024-10-31|NVDA,ARM|条件组件可复用|
|2024-11-29|APP|条件组件可复用|
|2024-12-31|APP|条件组件可复用|
|2025-01-31|MSTR,APP|条件组件可复用|
|2025-02-28|APP|条件组件可复用|
|2025-03-31|PLTR,APP|条件组件可复用|
|2025-04-30|PLTR|条件组件可复用|
|2025-05-30|PLTR|条件组件可复用|
|2025-06-30|PLTR,APP|条件组件可复用|
|2025-07-31|PLTR,APP|条件组件可复用|
|2025-08-29|PLTR,APP|条件组件可复用|
|2025-09-30|PLTR,APP|条件组件可复用|
|2025-10-31|PLTR,APP|条件组件可复用|
|2025-11-28|MU,PLTR|MU / UNMAPPED_LOOKBACK_DIVIDEND:2025-10-03|
|2025-12-31|WDC|条件组件可复用|
|2026-01-30|LRCX,STX,ABNB|LRCX / UNMAPPED_LOOKBACK_DIVIDEND:2025-12-03; STX / UNMAPPED_LOOKBACK_DIVIDEND:2025-12-24|
|2026-02-27|WDC|条件组件可复用|
|2026-03-31|LRCX,STX|LRCX / UNMAPPED_LOOKBACK_DIVIDEND:2026-03-04; STX / UNMAPPED_LOOKBACK_DIVIDEND:2026-03-25|
|2026-04-30|SNDK|条件组件可复用|
|2026-05-29|SNDK|条件组件可复用|
|2026-06-30|SNDK|条件组件可复用|

## 有限补证与编译结果

新增或复用9笔普通股息：原5笔加LRCX2025-12-03/2026-03-04、STX2025-12-24/2026-03-25；金额按事件当时名义单位，宣告日均不晚于除息日。MU原本地官方解析直接复用。SGEN2022-12-29→2023-03-31与ALXN2020-12-29→2021-03-31新增精确回溯会计无行动审核，不能把晚出的季报称作当时已知预测信息，仍非穷尽事件认证。

每股信号使用(P本日+D本日)/P前日；QQQ同公式、同63日期、现金收益0。股息计应收不等于可花现金。本地训练价为历史条件性坐标，使用当月名义decision_cost与训练末价的比例、截至decision已发生的已审拆股换算股息，不拿未来宣告股息加入先前决策。67个输入共26个股票股息窗口应用，均保存原名义金额、坐标除数和精确反算。没有计算策略回报、方差或缩仓建议。

编译会验证inventory及supplement已有预期source_hashes，并核对既有冻结trend manifest中的两窗训练、execution_inputs与QQQ等预期哈希，不只重新给当前文件打hash；QQQ两源重叠收盘和股息逐项必须相等。单位反算是同一训练价与因子的代数一致性检查，**不是独立价格来源核验**。

下一步必须由独立审查核验input及纯函数衔接。真实动态缩仓会改变资本与选股，未知新目标继续阻塞审核；不把固定旧目标输入冒充完整候选回测。

文件：
- `scripts/research/inventory_risk_budget_64d_20261105.py`：只读真实目标盘点。
- `scripts/research/prepare_risk_budget_64d_20261105.py`：仅构造输入，无方差/缩仓/收益回测。
- `tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json`：9股息与2无行动范围证据。
- `tmp/risk_budget_64d_inventory_20261105/risk_inputs.json`：67个arguments、book绑定、精确核算及源hash。

arguments与纯函数接口一致：target_quantities、decision_prices、tradable_equity、stock_gross_returns（SID→日期→有理数）、qqq_gross_returns（日期→有理数）、decision_date。

## 动态目标缺口的一次批量扩展

首轮账户早窗在2021-02-26选出PTON正目标，原固定目标输入没有这个pair，按设计阻塞，未伪装完整回测。原artifact保留不变。先编译PTON单pair，随后按授权盘点既有67月best_by_k保存frontier支持，共6531个日期/股票pair；这不是新增选股搜索或新投资域。

其中原113pair保持，2729个额外pair已具备完整64日、HTTP200显式div/splits请求及原文件hash、区间无报告事件、训练价与原收盘固定比例，故一次性零网络编译；其余涉及事件、CSV或复杂坐标者不放行，不扩大无关补证。

批量artifact：`tmp/risk_budget_pair_extension_20261105/risk_inputs_zero_event_frontier_v1.json`，SHA256 `2860c13da7db7b888581b4c4e60090f87e92b19c55ed3dd2b0e22c0e45a7cdbc`；父版SHA256 `c1fbdb4891d573be29657238dc8f4718d7685edb6769edbada1e3ceeae1c4592`。原67窗目标、权益、QQQ及原股票收益不变，追加pair不代表赋予其目标仓位。

编译10.86秒，独立核验1.84秒，逐pair核验171927个原始日收益比值及请求凭证、完整父版差异、全部sourcepins。独审代码未调用编译helper。来源仍为条件性供应商无报告事件，不升级成官方穷尽/PIT认证。

复现代码：`scripts/research/extend_risk_budget_zero_event_frontier_20261105.py`、`scripts/research/audit_risk_budget_zero_event_frontier_20261105.py`。报告为同tmp目录的 `zero_event_compilation_report.json` 与 `zero_event_independent_review.json`。没有启动账户恢复；须根审核后统一恢复，不能逐股重跑。
