# 2021—2023历史价格日期覆盖完成

冻结的2021年1月至2023年12月连续范围没有移动。重新运行现有覆盖检查，36个月、3,658个股票月份窗口的有效训练及旧证券可交易日价格日期缺口为零。依法不足253日的新股排除仍保留；并购终止后的旧证券不制造行情，另由转换权益处理。因此本结论不等于公司行动完整、输入全部准入或策略收益验证成功。

本轮实际补齐：

| 证券 | 固定价格候选 | 结果 |
|---|---|---|
| CERN | GitHub历史表→ChartExchange→Quiver | 613日，2020-01-02—2022-06-07 |
| XLNX | tsaustin历史表→ChartExchange→Quiver | 534日，2020-01-02—2022-02-11，原17日全部补齐 |
| SGEN | PaulMooney历史表→ChartExchange→Quiver | 995日，2020-01-02—2023-12-13 |
| SPLK | PaulMooney历史表→ChartExchange→Quiver | 1,006日，2020-01-02—2023-12-29 |
| WBD | Zenodo记录12566468 | 2020—2023年1,006日；前身需绑定DISCA一比一转换证据 |

前四只由`scripts/build_recent_price_bridges.py`重建，固定采用Quiver完整可见末段、之前ChartExchange、再之前指定归档。切换不读取策略表现，不择取逐日较有利价格；原始差异、来源哈希与切换日期写入审计。使用原始OHLC，不使用adjusted close代替。原始归档2022-12-12疑似盘中尾行不进入所选来源区段。

XLNX归档原文件2019-08-20存在非法OHLC，首次全文件校验因此拒绝。修正为仅读取冻结研究所需2020年及之后的区间，未修补或删除原文件。所有进入候选的2020年以后数据仍逐行验证。该修正不能用于声称2019年数据可靠。

参考日期来自已保存AAPL响应，尚非独立交易所日历；覆盖脚本仍将`units_identity_actions_admitted`与`compiler_ready`保持false。来源后来归档不等于当时即可获得；这里只声明历史行情内容可供核查，策略决策不得读入未来信息。

运行入口：

```powershell
D:\python\python.exe scripts/build_recent_price_bridges.py
D:\python\python.exe scripts/audit_recent_monthly_price_routes_v3.py
```

产物分别位于`tmp/recent_price_bridges_20261026/`与`tmp/qqq_20201231_anchor_20261025/monthly_price_routes_v5_fields.json`。原始第三方行情仅保留本地，不推送GitHub。

下一步停止对已齐日期反复找源，完成训练价格坐标、决策名义成本和实际持仓路径公司行动接入，再运行冻结的V27基准及有限候选比较。当前没有新的牛熊年化/回撤成绩，不能宣称最大回撤目标已达成。
