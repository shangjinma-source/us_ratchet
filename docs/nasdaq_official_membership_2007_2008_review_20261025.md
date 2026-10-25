# 2007/2008 Nasdaq100官方重组核查

本轮检查三类入口：Nasdaq官网年调及附件、Nasdaq自行发布的GlobeNewswire版本、Stericycle SEC公告。原始HTTP下载均403，错误正文及SHA256保存在 `tmp/nasdaq_official_membership_20261025/manifest.json`，不能误称原公告下载成功。web工具可读Nasdaq正文与2008 PDF；已把核对出的结构化事件写入同目录 `verified_events.json`，明确这是解析工具核验，不是原始PDF字节证明。

|公告日|生效开盘|加入|移除|
|---|---|---|---|
|2007-12-14|2007-12-24|HOLX FMCN HANS STLD SRCL|ERIC PTEN ROST SEPR XMSR|
|2008-12-12|2008-12-22|ADP FSLR LIFE ROST MXIM ILMN PPDI ORLY URBN JBHT WCRX|AMLN CDNS DISCA LAMR LEAP LVLT PETM SIRI SNDK VMED WFMI|

官方来源：[2007正文](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-annual-re-ranking-nasdaq-100-index-1)、[2008正文](https://ir.nasdaq.com/node/62366)、[2008 PDF](https://ir.nasdaq.com/static-files/fe342fcb-28a8-4aa9-9ff6-c4bda51943e7)。2007正文内附件实际是November Market Performance Statistics，内容与链接标题不符，不能用来证明成员变更。

这两组事件可校验历史CSV年度增删、当时ticker、公告与生效时序；并非100只完整成员锚点，不能单独消除LMCK/NDOI污染。未擅自删除任何股票。第三入口 [Stericycle SEC公告](https://www.sec.gov/Archives/edgar/data/861878/000086187807000032/ex991207.htm) 的web结果独立确认SRCL于2007-12-24加入；该发行人单股公告不是全指数名单。

额外线索：jmccarrell/n100tickers最新changelog宣称已扩展2007—2014并修复当时ticker（SYMC/PCLN等）及2007 Henry Schein替换Maxim缺漏。仍是二手重建，须以以上公告作交叉验证，不运行其代码，不将其自称100名单当成官方锚点。本轮未取得QQQQ当年完整持仓；即使取得也须区分基金持仓与指数正式成员。

## 完整持仓交叉证据已取得

[QQQQ自身SEC 485BPOS](https://www.sec.gov/Archives/edgar/data/1067839/000120677408000229/powershares_485bpos.htm) 于2008-01-31提交，其中2007-09-30 Schedule of Investments完整100公司名单已通过web解析保存为 `tmp/nasdaq_official_membership_20261025/qqqq_20070930_holdings.csv`。字段公司名称、持股数、美元市值；100项市值合计20,559,646,460，精确吻合披露总投资金额。`qqqq_manifest.json`绑定解析证据hash与表hash。直接HTTP仍403，因此这是web解析表，不冒称原始SEC字节下载成功。

该表是基金持仓，日期早于目标起点且不含ticker/CUSIP，不能直接认定指数正式名单。但它为公司层面完整分母提供了独立交叉证据；随后可逐一结合2007年10月、12月官方变更。特别包含Novellus、Monster Worldwide、NII Holdings、Liberty Media和Liberty Global，应据此审查原污染名单，而非按现代ticker直接联接。

最新jmccarrell/n100tickers的2007—2010 YAML及测试、算法文本已锁定commit `2d7be392976e339174ece643acbb00a53e973eb8`下载，见 `jmccarrell_manifest.json`。代码未执行。该项目2007年100标签锚点来自当年Wikipedia快照，其Jan1名单又是从Feb1反推，故不能替代官方证据。两套来源可先做公司/事件层面交叉比对。

## 独立金额与价格单位抽查

主线程重新读取100行，确认公司名称无重复、市值合计20,559,646,460与SEC正文一致。另以2007-09-30披露市值除持股数，对照WIKI 2007-09-28收盘价：MSFT、QCOM、INTC三者差额小于0.01美元；AAPL反推约153.54美元，而WIKI为153.47美元，差约0.07美元。该差异待核估值及收盘价来源，不能直接判某方错误或强行改价。调整收盘价与这些名义股数坐标明显不同。

样本输出在`tmp/nasdaq_official_membership_20261025/nominal_price_spot_check.json`。四个价格样本不认证完整价格史、公司行动或成员资格；仍保持未准入状态。
