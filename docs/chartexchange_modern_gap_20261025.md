# ChartExchange：MXIM 补齐，XLNX 缺口缩至 17 日

仅请求 [MXIM](https://chartexchange.com/symbol/nasdaq-mxim/historical/) 与 [XLNX](https://chartexchange.com/symbol/nasdaq-xlnx/historical/) 两个公开历史页面，各一次 HTTP 200。每页实际 370 行，字段 Date/Open/High/Low/Close/Change/Volume/Change Since。未运行网站代码，未注册或翻猜参数；XLNX HTML 没有 form 或可见更早/下一页链接，因此停止该入口。

固定来源优先级：Quiver 使用完整可见末段；此前使用 ChartExchange；更早使用已有 GitHub archive。未按收益或误差择源；volume 与 adjusted close 均不进入价格候选。

| 标签 | 页面覆盖 | 合成结果 | 参考日历缺口 | SEC 2020-12-31 名义锚 |
|---|---|---|---|---|
| MXIM | 2020-03-10—2021-08-25 | 416 行，2020-01-02—2021-08-25 | 无 | 88.649999866 vs 88.65 |
| XLNX | 2020-08-26—2022-02-11 | 517 行，2020-01-02—2022-02-11 | 2020-08-03—08-25，共17日 | 141.770000143 vs 141.77 |

参考日历来自已保存 AAPL Yahoo 时间戳，非独立交易所日历。两候选无多余日期及非法 OHLC；XLNX 明确标为 INCOMPLETE_PRICE_CANDIDATE，不能正式用于完整策略。

重叠诊断保留差异：MXIM archive/ChartExchange 101 日 OHLC 全部在半美分容差内，volume 全不同；ChartExchange/Quiver 253 日有 13 个 OHLC 字段超过容差，最大 0.31 美元，volume 4 日不同。XLNX ChartExchange/Quiver 254 日有 11 项超差，最大 0.23 美元，volume 3 日不同。固定 Quiver 优先使其覆盖区不会任意混源；这些供应商差异不隐藏，未声称每笔行情完全一致。

实际原始 HTML、CSV、所有输入输出 hash、重叠明细及可复现脚本 `build_candidates.py` 位于 `tmp/chartexchange_gap_20261025/`。MXIM 仅 price-only candidate，收购/股息/身份/后续持仓转换另行认证；没有改生产或提交。
