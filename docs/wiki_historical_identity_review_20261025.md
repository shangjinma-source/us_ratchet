# WIKI历史代码身份核查

本轮对实际WIKI覆盖统计与官方证券资料作交叉检查。不能将字符串匹配当作历史证券身份认证，也不能把全部未匹配项称为退市缺失。

| 历史标签 | 查询线索 | 实际WIKI覆盖 | 判断 |
|---|---|---|---|
| HANS | MNST | 1995-08-18起；2007—2009有756行 | 公司公告确认2012-01-09从HANS改为MNST；可作为历史查询路线，仍须核对价格单位和后续重组 |
| 2014年前GOOG（Class A） | GOOGL | 2004-08-19起；2007—2009有756行 | 官方年报确认2014-04-03旧Class A改为GOOGL；WIKI的GOOG从2014年开始，不能回填2008年 |
| RIMM | BBRY，后续BB待查 | WIKI三个标签均不存在 | 官方资料确认美股2013-02-04改BBRY，当时BB是多伦多代码；不能把不同市场代码直接视作同一行情 |

一手资料：

- [Hansen公司更名公告](https://www.globenewswire.com/news-release/2012/01/05/464838/0/en/Hansen-Natural-Announces-Corporate-Name-Ticker-Symbol-Change.html)
- [Google 2014年报](https://abc.xyz/assets/investor/static/pdf/2014_google_annual_report.pdf)
- [BlackBerry 2014年度资料](https://www.blackberry.com/content/dam/blackberry-com/Documents/pdf/financial-reports/2014/q4fy2014/Annual_Information_Form_Fiscal_2014.pdf)

本地统计依据：`tmp/github_history_routes_20261025/wiki_coverage.json`，原归档来源与SHA见同目录下载manifest。首末日期和行数不认证交易日完整性。上述查询路线尚未写入正式security_id映射，未产生经济成绩。

其他未认证线索：WIKI有SYMC、WFM、UAL、LINTA相应历史，候选成员却包含NLOK、WFMI、UAUA、QRTEA；必须分别区分单纯改名、合并和追踪股重组，不能统一字符串替换。ERIC、FLEX、INFY、LOGI、RYAAY、TEVA等缺失也可能源于数据集收录范围，继续其他免费来源查询。
