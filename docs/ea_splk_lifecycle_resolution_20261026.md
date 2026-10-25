# EA与SPLK旧窗口覆盖复核

两项均无需新下载股票行情。EA所需15日已保存在旧执行输入的第二来源段，先前矩阵只看whole_source漏读segments；SPLK余9日属于终止交易之后，不能补造价格。原冻结输入未改，未运行经济回测。

EA：Nasdaq官方 https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-545 确认最后交易日2026-08-04，8月5日停牌，故7月10日至30日仍需行情。tmp/next12_ea_alternate_source_20261014_v1/web_observation.json 已存6月30日至7月30日22日OHLC，包含缺口15日，与旧prepared对应段逐字段完全一致且OHLC合法。与旧CSV重叠7日有2个字段差异，保留在review中。旧方案使用整体第二段，不是挑缺失日混填。

EA来源局限仍是StockAnalysis/S&P网页观察、split-adjusted Close，非原始HTTP认证；此次本地复核不提升为新认证行情，不把Close当含股息总回报。

SPLK：Nasdaq官方 https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-132 确认最后交易日2024-03-15，当日20:00盘后停牌；3月18日盘前收购完成，3月19日起正式停牌，每股现金对价157美元。Nasdaq3月8日指数公告确认LIN在3月18日盘前替换SPLK。现CSV至3月15日，余9日不是上市行情缺口。

成员移除和持仓权益分别处理：若策略持有SPLK，收购时必须转换为157美元/股现金权益，不能删除持仓价值；未到账权益不用于新买入。官方终止与对价不等于券商到账日，不捏造卖出成交或当日付款。

实际原文、hash、重叠差异与日期清单：tmp/ea_splk_lifecycle_20261026/review.json 和同目录fetch.json。两份Nasdaq原文及Cisco完成公告均HTTP200。指数公告直接HTTP403，官方网页索引内容已核。没有改正式策略或账户。
