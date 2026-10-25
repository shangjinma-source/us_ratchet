# 2022 年 1 月候选域普通股息扫描

仅使用已编译月度诊断的 101 个证券域及其保存来源，不扩大选股。94 份 Yahoo 响应实际遍历 dividends 字段，7 份替代 CSV 无事件流，明确列为未覆盖，不能据价格文件认定没有股息。

| 股票 | provider 除息事件日 | provider金额 USD | 价格坐标因子 | 官方本轮核验 |
|---|---|---:|---:|---|
| CMCSA | 2022-01-04 | .234302 | 1.067 | 原每股 .25；record 1/5；pay 1/26 |
| CSCO | 2022-01-04 | .37 | 1 | ex 1/4；record 1/5；pay 1/26；原每股 .37 |
| KDP | 2022-01-05 | .188 | 1 | 原每股 .1875；record 1/6；pay 1/20 |
| MRVL | 2022-01-06 | .06 | 1 | 未在本批扩查 |
| INTU | 2022-01-07 | .68 | 1 | 未在本批扩查 |
| PAYX | 2022-01-28 | .66 | 1 | 未在本批扩查 |
| TXN | 2022-01-28 | 1.15 | 1 | 未在本批扩查 |

CMCSA provider 金额 × 1.067 约为 .25，说明不能直接用事后坐标金额计入历史名义现金；以官方 .25 为准。KDP provider .188 有三位小数舍入，真实官方 .1875，不能把价格因子 1 当金额必然精确的证明。CSCO 金额一致。

官方来源：[Comcast 股息表](https://www.cmcsa.com/stock-performance/dividends-and-stock-splits)、[Cisco 股息表](https://investor.cisco.com/stock-info/dividend-history/default.aspx)、[KDP 2021-12-07 公告](https://www.keurigdrpepper.com/keurig-dr-pepper-declares-quarterly-dividend-86/)。CMCSA/KDP 公告提供 record/pay/amount，ex 日仍来自本地 Yahoo，未机械由 record 日期推算。Cisco 官方表同时列出 ex 日。

requests 实取 CMCSA/KDP 403、Cisco 200；Cisco HTML 未找到目标历史表行，因此三项官方字段核验均明确保存为 web 工具文本，不把成功 HTTP 本身冒充完整行证据。源网址、原响应/hash、文本摘录、各 provider 原事件/hash 全保留。

替代 CSV 尚无全量事件流的七只：ANSS、ATVI、EA、SGEN、SPLK、WBA、XLNX。本列表只是候选暴露事件，未按实际持仓删事件。入账应以除息日交易前持仓取得权益；未到支付日不可用于买入，缺支付日保持应收。所有金额是 gross，税率未知保持 null，不臆造用户净到帐。月底 PAYX/TXN 即使未来支付，也不能遗漏当月应收。

证据：`tmp/january2022_dividend_scan_20261026/january_dividend_evidence.json`；原始扫描 `provider_january_events.json`；官方文本 `official_web_selected_text.json`；下载 manifest 与原响应。未改根/scope 输入或运行经济搜索。
