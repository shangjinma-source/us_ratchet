# 剩余旧股行情：两条有限路线核查

本次未重复QSTK/Yahoo/WIKI。未运行第三方代码，未购买注册。

1. [QuantQuoteHistoricalIngest](https://github.com/ellisvalentiner/QuantQuoteHistoricalIngest) 实际文件树只有导入脚本，无行情。只读脚本发现旧zip地址https://quantquote.com/files/quantquote_daily_sp500_83986.zip；HEAD实测见tmp/github_gap_routes_20261025/quantquote_head.json。官方历史页面web返回404。仓库README描述当时活跃S&P500 1998—2013数据，全拆股/股息调整；不能推断包含NIHD/VMED或已退市CEPH。未确认目标成员，因此未下载大包。

2. [azymnis/python-stocks](https://github.com/azymnis/python-stocks) 搜索命中NIHD，但实际nasdaq100.csv为代码列表，stockResults.csv为2010-02-18—2010-03-18模拟统计mean/std/z-value，不是逐日OHLC。完整文件树12项无历史价格文件。故此路线不补价格缺口。

证据文件树、README、只读脚本文本、结果CSV样本、请求状态及hash均在tmp/github_gap_routes_20261025/。本轮未新增可准入行情，不能把代码存在当作价格覆盖。
