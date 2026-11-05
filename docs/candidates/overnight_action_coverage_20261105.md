# 隔夜名单：已有无行动证据及SMCI边界复核

2026-11-05，单次限定本地核查，无下载、模型调用、选股或经济回测。原主线运行源码与输入未改。明细保存在 `tmp/overnight_preflight_20261105/local_action_review.json`。

## 无行动索引缺失不等于仍需补资料

对照原 `tmp/trend_2021_2023_20261026_v1/execution_inputs.json` 和 `tmp/trend_2024_2026_20261026_v1/execution_inputs.json` 的 action_review，逐一核每个实际隔夜区间而非只比较首尾日期。引用原件均验证已有预期 source_hashes；后窗六只另实际调用 `scripts/run_old_continuous_probe_v4.py::validate_absence_review`，原请求/receipt/started、选中源及区间检查全部通过。

|股票|本路径隔夜配对|已覆盖|未覆盖|已有审查范围|
|---|---:|---:|---:|---|
|ALXN|21|21|0|(2021-03-31,04-30]及(04-30,05-03]|
|SGEN|19|19|0|(2023-03-31,04-28]及(04-28,05-31]|
|ABNB|38|38|0|(2023-12-29,2026-07-30]|
|APP|208|208|0|同上|
|ARM|43|43|0|同上|
|PDD（后窗）|19|19|0|同上|
|PLTR|190|190|0|同上|
|SNDK|61|61|0|(2025-02-13,2026-07-30]|

ALXN复用 `tmp/alxn_april_action_review_20261026/official_evidence.json` 和 `tmp/alxn_may_action_review_20261026/official_evidence.json`；后者明确最后开盘卖出必须在5/3完成，不覆盖延迟成交。SGEN复用 `tmp/sgen_april_action_review_20261026/official_evidence.json`。这些是官方原文解析及回溯会计事实的条件性范围审查，非穷尽无行动认证，不能当作当时的预测信息。

后窗六只复用 `data/cache/research/current_raw_capture_20261013_v1/`、`current_raw_capture_20261014_v1/` 下对应 ticker 的 `.response.bin/.receipt.json/.started.json`。验证的是明确请求 div/splits、成功完整响应及已选源区间，不是所有可能公司行动的全球认证。本轮不需要再次下载这些无行动材料。

## SMCI：已有事实足够准备隔夜整仓卖出转换，尚未完成执行实现

实际问题区间只有2024-09-30收盘买旧SID→10/1开盘卖。原review中的 `SMCI_SPLIT_IDENTITY_20241001` 与 `reviewed_split_events(review, envelope)` 匹配通过，全部引用原件hash复核通过：

- 旧SID `security:0001375365:86800U104` → 新SID `security:0001375365:86800U302`，一股变十股，无耦合分配；整数旧股不会产生零碎股。
- 官方公告来源 `https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-451` 的既存本地解析及身份/行情映射由 review 的 source_references 绑定，主索引 `tmp/midwindow_identity_bridge_20261026/review.json`、`tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json`。不得将只有身份事实的单份文件当成完整执行授权。
- 公告日9/24；法律生效9/30美东17:00；新单位开始交易10/1。9/30收盘仍旧单位，不能提前把买入股数乘十。原名义close约416.3999938964844，新SID 10/1 open=41.75美元；原价存在，无需补造旧SID 10/1 open。
- 固定O1可在9/30成交后、10/1卖出前将 q 股旧仓迁为10q股新仓，按新单位开盘卖；独审需证实没有重复现金/股息/收益及身份丢失，成交成本按实际新股数乘新价格计算。这是本支线全清规则，不要求移植原V27跨身份峰值状态，不放宽主线 `SAME_ID_SPLIT_ONLY`。

研究上已有转换事实和价格，**可开始准备固定O1经济对照的隔离实现与测试**；并非本次已经授权任意账户转换或证明真实券商即时可卖。实际汇丰到账/订单可达仍未知；如10/1无法成交，延迟持仓不是本次已认证路径。

## 仍须落实，不能用本报告代替

本次八只无行动区间无未覆盖；SMCI不再是需要外部补价的问题，但独立隔夜账本转换尚未实现/验收。前次预检七个个股股息的实际 entitlement/payment 接线、本支线固定提交数量/现金拒单、成本压力、会话末端及同名单持续持有控制臂仍需实现并独审。QQQ paydate未知继续不可花应收。这里没有收益、回撤或实盘可执行结论，不再扩大资料核查。
