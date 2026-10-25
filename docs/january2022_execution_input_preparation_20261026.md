# 2022 年 1 月真实执行输入已组装

`scripts/prepare_january2022_execution_inputs.py` 已实际消费编译好的训练参数，生成 `tmp/qqq_20201231_anchor_20261025/january2022_execution_diagnostic.json`。保留 101 只证券、100 个发行人，2021-12-31 启动决策到 2022-01-31 终端共 21 个参考会话，包含 20 个实际执行日。只有一条月度决策，1/31 不触发 2 月配置。

每只证券继续使用训练时固定来源与 hash，按训练单位审核确定的固定名义坐标还原实际 OHLC；没有按结果择源。所有 2,121 条日线均经正数/高低价关系检查，每个启动 close 与 compiler decision_cost 使用 Fraction **精确相等**。已真实调用 `assemble_monthly_execution_inputs_v4` 成功，完整 `prepared`、`assembled`、`ohlc` 及来源核验均保存。没有调用搜索或经济执行。

**尚未授权经济运行**，实际而非假设地检查动作后保留两类明确问题：

1. 94 个固定 Yahoo 源带事件流，研究月未见 split/distribution 字段事件，发现 7 条股息：CMCSA、CSCO、INTU、KDP、MRVL、PAYX、TXN。股息单位与付款状态待映射；尤其 CMCSA provider 金额 0.234302 处在后续坐标，而 KDP 的 0.188 存在源报价精度，不能简单默认原始名义金额。`dividend_events=null`，不把未知写成空数组。
2. 7 个固定 CSV 源（ANSS、ATVI、EA、SGEN、SPLK、WBA、XLNX）无事件字段，不能从价格完整推导没有现金股息/其他行动。列为定向事件源核验，不要求重新获取已完整的价格。

输出的 `runner_execution_authorized=false` 和 `execution_blockers` 明确阻止把空动作占位误当审核完成。未来 EXC 分拆因子仅用于本月价格尺度，不提前在账本创造权益；真实 EXC 分拆在 2 月执行域之外。下一步可独立准备同一真实输入的选择探针，但完成收益回放须先补上述动作条件。

```powershell
D:\python\python.exe scripts/prepare_january2022_execution_inputs.py
```
