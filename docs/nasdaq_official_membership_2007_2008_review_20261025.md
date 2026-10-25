# 2007/2008 Nasdaq100官方重组核查

本轮检查三类入口：Nasdaq官网年调及附件、Nasdaq自行发布的GlobeNewswire版本、Stericycle SEC公告。原始HTTP下载均403，错误正文及SHA256保存在 `tmp/nasdaq_official_membership_20261025/manifest.json`，不能误称原公告下载成功。web工具可读Nasdaq正文与2008 PDF；已把核对出的结构化事件写入同目录 `verified_events.json`，明确这是解析工具核验，不是原始PDF字节证明。

|公告日|生效开盘|加入|移除|
|---|---|---|---|
|2007-12-14|2007-12-24|HOLX FMCN HANS STLD SRCL|ERIC PTEN ROST SEPR XMSR|
|2008-12-12|2008-12-22|ADP FSLR LIFE ROST MXIM ILMN PPDI ORLY URBN JBHT WCRX|AMLN CDNS DISCA LAMR LEAP LVLT PETM SIRI SNDK VMED WFMI|

官方来源：[2007正文](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-annual-re-ranking-nasdaq-100-index-1)、[2008正文](https://ir.nasdaq.com/node/62366)、[2008 PDF](https://ir.nasdaq.com/static-files/fe342fcb-28a8-4aa9-9ff6-c4bda51943e7)。2007正文内附件实际是November Market Performance Statistics，内容与链接标题不符，不能用来证明成员变更。

这两组事件可校验历史CSV年度增删、当时ticker、公告与生效时序；并非100只完整成员锚点，不能单独消除LMCK/NDOI污染。未擅自删除任何股票。第三入口 [Stericycle SEC公告](https://www.sec.gov/Archives/edgar/data/861878/000086187807000032/ex991207.htm) 的web结果独立确认SRCL于2007-12-24加入；该发行人单股公告不是全指数名单。

额外线索：jmccarrell/n100tickers最新changelog宣称已扩展2007—2014并修复当时ticker（SYMC/PCLN等）及2007 Henry Schein替换Maxim缺漏。仍是二手重建，须以以上公告作交叉验证，不运行其代码，不将其自称100名单当成官方锚点。本轮未取得QQQQ当年完整持仓；即使取得也须区分基金持仓与指数正式成员。
