# Candlestick GitHub 归档：实际补齐 ALXN 时间缺口的候选

只检查一个仓库、下载三个 CSV，未运行仓库代码。真实 GitHub commit `2747eab3d310e79ce82a6d237f18ea6f4d0be6a3`，提交时间 2020-08-10。来源：[hackingthemarkets/candlestick-screener](https://github.com/hackingthemarkets/candlestick-screener/tree/2747eab3d310e79ce82a6d237f18ea6f4d0be6a3/datasets/daily)。未发现 LICENSE 文件，数据再分发许可未确认；原始行情仅放 tmp。

| CSV | 实际行数 | 起止日期 | 与现有 Quiver 的连接 |
|---|---:|---|---|
| ALXN | 147 | 2020-01-02—2020-07-31 | Quiver 从 2020-07-20 开始，有 10 日重叠；可以补原 April→July 时间缺口 |
| MXIM | 147 | 同上 | 仍缺 2020-08-03—08-24 |
| XLNX | 147 | 同上 | 仍缺 2020-08-03—2021-02-10 |

字段 Date/Open/High/Low/Close/Adj Close/Volume。ALXN 重叠 10 日：40 个 OHLC 比较中 38 个在 0.00501 美元容差内；7/24 High 和 7/27 Low 差约 0.01 美元，10 日成交量全部存在差异，保留诊断而不默认为相同。价格容差考虑 Quiver 仅保留两位小数。MXIM、XLNX 的 Adj Close 与 Close 不同，不可混用。不能据此宣称公司行动、证券身份和全域交易日覆盖已经认证。

实际文件、来源、SHA256、commit/tree 和重叠诊断保存在 `tmp/candlestick_gap_probe_20261025/`。所有文件 `admitted=false`，未注入回测。此路线已完成，不继续猜其他文件或 ticker。

按固定优先级生成 ALXN price-only candidate：2020-07-20 起全用 Quiver，此前使用 GitHub archive；不根据收益择源。结果 390 行，2020-01-02—2021-07-20，相对已保存 AAPL 时间戳参考日历无缺失、多余、重复或非法 OHLC；其中 2020 年有 253 个收盘。SEC 2020-12-31 市值 429637502 / 股数 2749856 = 156.240000203647，与候选 close 156.24 差 0.000000204 美元。参考日历不是独立交易所日历，证券经济行动仍单独准入。构建脚本 `build_alxn_candidate.py`、输出 `ALXN_price_candidate_2020_2021.csv` 和 `ALXN_price_candidate_audit.json` 保存全部输入输出 hash；volume/Adj Close 不参与该价格候选，已发现差异仍保留。
