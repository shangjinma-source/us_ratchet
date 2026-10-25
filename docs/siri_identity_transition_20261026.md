# SIRI 2024 年 9 月身份转换

[Nasdaq ECA2024-421](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-421) 与 [发行人 SEC 完成公告](https://www.sec.gov/Archives/edgar/data/908937/000110465924098372/tm2423473d6_8k.htm) 确认：纽约当地时间 2024-09-09 16:05 Liberty 分离先发生，18:00 才是旧 Sirius 股份并购转换。新证券从 9/10 开始交易。

旧 SIRI 普通股 CUSIP **82968B103** 每 10 股取得 1 股新 SIRI **829933100**；零股现金替代。**0.8375 是 Liberty 跟踪股 LSXMA/B/K 的比例，不能用于旧 SIRI。** 旧上市母公司更名 Sirius XM Inc.，成为新母公司子公司；原 Liberty Sirius XM Holdings Inc. 更名 Sirius XM Holdings Inc.。后继报告使用 CIK 0000908937，但 CIK 沿用不代表法律发行人和 CUSIP 未变。

本地旧标识为 security:0000908937:82968B103。新标识由 assembler 显式分配，不能把 9/10 后报价继续挂旧标识。保存证据与 hash：[review.json](../tmp/siri_identity_transition_20261026/review.json)。原文为 web 工具解析文本；Nasdaq 写 EST，而 SEC 明确纽约时间，建账应使用 America/New_York，避免九月时差歧义。

真实零股现金价格、付款日期和可用时间仍未知。此证据解除比例／CUSIP／阶段事实缺口，不等于跨 SID 执行与独立 reviewer 已接通；不能用 provider 0.1 普通拆股直接放行。旧生命周期及接口清单中的身份待核状态由本新证据补充，旧 hash 文件未修改。
