# EA价格缺口修正：停牌后不是缺失日线

实际取得[Nasdaq Trader ECA2026-545](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-545) HTTP200原HTML，公告确认EA最后交易日2026-08-04、8/5起停牌、并购现金对价每股210美元。SEC同次[8-K](https://www.sec.gov/Archives/edgar/data/712515/000114036126031157/ef20079099_8k.htm)网页工具正文交叉确认8/4合并完成；直接下载SEC返回403，不宣称本地保存了SEC原文。

因此原差集的22个空白日期必须拆开：7/31、8/3、8/4三日仍需真实行情；8/5之后19个工作日不应要求交易所日线，不能前向填成可以交易的价格。若7/31域确认后策略持有EA，还需显式转换并购权益并处理可用现金到账时点；210美元对价不等于8/4即可再投资的可用现金。

Nasdaq页面带UPDATED标记，现代下载不能证明所有正文在页面标注7/31当日已公开。此证据用于确认实际生命周期与执行会计，不能把8/4已完成结果回填到7/31选股信息。成员身份、其余公司行动及原价格单位仍另核验。未创建价格、未跑新回测、未修改生产。

本地原文及receipt、gap_review.json位于tmp/ea_merger_source_20261104；脚本scripts/research/review_ea_trading_end_20261104.py验证原文摘要和明确事实后重新分类旧差集。原HTML不上传Git。

## 三个真实交易日已取得，历史重叠差异保留

取得[ChartExchange历史页](https://chartexchange.com/symbol/nasdaq-ea/historical/)原HTML及三日OHLC；[StockAnalysis表格](https://stockanalysis.com/stocks/ea/history/)网页工具显示相同三日OHLC，直接下载403，仅保存明确标注的网页观察。两者成交量不同，不准入成交量，不声称独立原始行情认证。

prepare_ea_final_prices_20261104.py读取367个历史重叠日，发现8日各一个OHLC字段相差0.01美元，其中2日为收盘。最后重叠日7/30全部OHLC一致。候选状态保留BLOCKED_PRICE_OVERLAP，不覆盖旧冻结历史或隐去差异。三日价格已取得，尚未拼接回测；后续应保留原历史并明确新段来源及差异影响，不能再报告“EA三日行情无来源”。私人证据tmp/ea_final_prices_20261104。
