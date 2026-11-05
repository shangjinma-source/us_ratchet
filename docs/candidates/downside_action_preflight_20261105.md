# Downside 宽篮子账户候选：公司行动预检

2026-11-05，只读审阅现有代码和证据；未启动搜索、经济回测或网络获取，未改变生产。不限持股数会扩大潜在行动暴露，以下不是全域行动认证，也不证明每个缺口一定触发。

## 已支持的实际路径

- 草稿入口 `scripts/research/run_downside_account_candidate_20261105.py` 复用原账户账务和 `backtest/monthly_exit_core_research_adapter.py`；后者仅接受有精确证据的同 SID 拆股，迁移峰值、前收盘及单位。不能把底层账本存在某类事件功能当作整个风险路径已支持。
- 原执行输入为 `tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json`（早窗）及 `tmp/old_continuous_baseline_20261026_v9/execution_inputs.json`（后窗）。早窗 assembled 的 actions、distribution_events、supported_conversions、cash_stock_merger_events 均空；后窗仅有 SMCI 2024-10-01 split_identity，其余三类为空。
- 行动审查来自 `tmp/trend_2021_2023_20261026_v1/execution_inputs.json`、`tmp/trend_2024_2026_20261026_v1/execution_inputs.json` 的 action_review。草稿合并 `tmp/equal_four_20261105/source_review/admitted_supplement.json` 的审查及真实 dividend_events；后窗复用已冻结 WBD legacy absence adapter。
- `scripts/run_old_continuous_probe_v4.py::admit_split_liquidation` 仅准 SMCI 已核事实下的换月整数全清：行动日等于首次执行日、旧仓正数、新仓零、新旧 SID 目标均零且换算后整数。持续持有或保留新目标不在许可内。独审严格零暴露证明亦不能冒充新持仓转换适配。

## 可按精确范围复用的证据

- `tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json` 保存 NVDA、CEG、MU、LRCX、STX 共九笔股息及 ALXN `(2020-12-29, 2021-03-31]`、SGEN `(2022-12-29, 2023-03-31]` 条件性回溯无行动审查。其原用途包括训练风险输入，不能直接当成执行事件或审查 schema；须逐项映射、核来源 hash、避免重复，再接入实际账本及 gate。回溯报表证明不是当时已知选股信息，也不扩展至区间外。
- `tmp/azn_dividend_independent_20261105/review.json` 与 `batch_review.json`：历史 ADS 为半普通股，不能将普通股现金额直接记给 ADS。发行人支付日不等于汇丰真实到账证明，税前研究假设需保留。
- `tmp/avgo_independent_20261105/review.json`：2024-03-20 股息对应拆前名义单位 5.25 美元、付款日 3/29，7/15 十拆一；须保持行情名义坐标一致。休市付款日不得静默改成上一交易日。
- 上述新增材料并非全部已接入当前草稿。仅放行 gate 而不注入正确股息/行动及风险单位迁移，不算完成。

## 保留阻断

1. **ALXN 2021-07-21 混合并购**：`tmp/alxn_economic_events_20261025/schema_mapping.json` 明示每股 60 美元及 2.1243 AZN ADS，零碎股按交换代理处置净款分配；付款、交股日期和零碎股金额未定，`existing_fractional_schema_compatible=false`。原 assembled 没有该事件，不能仅凭条款放行。
2. **AZN 2026-02-02 ADS 转普通股**：现有资料不足以解除整条执行路径限制；原 assembled 无完整转换事件，风险目标/峰值身份迁移未支持，奇数 ADS 零碎权益及价格单位边界仍需审查。供应商 split 记录不是完整转换授权。
3. **SMCI 持有跨身份拆股**：原风险适配器仍 `SAME_ID_SPLIT_ONLY`。除上述既有全清路径或独立证明真实零暴露外，不准继续。

旧四股扫描 `docs/candidates/equal_four_batch_scope_20261105.md` 可作潜在问题索引；其旧缺口数量不能当作最新全部缺失数量，更不能当作当前宽篮子实际暴露清单。

## 固定运行及失败验收边界

根线程已批准每窗 **10,800 秒**、每月 **600 秒**、早/后窗最多 **36/31 次新选择**，无需再次请求用户许可。仅固定规则独立两窗，不调参、不改变生产。

启动前冻结代码、规则、输入及证据 hash；实际路径仍逐月运行公司行动 gate。遇真实暴露无法准入，保存选择、目标、exposure 原因、累计选择/耗时和 source pins，报告“未完成及具体缺口”，不按不完整收益评价候选。不删证券、清空事件、改变目标或把未到账权益当现金来绕过门槛；恢复须累计已有预算，不从首次失败重新取得额度。
