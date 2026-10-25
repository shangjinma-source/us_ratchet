# GitHub 历史行情路线实证（2026-10-25）

用户未指定年份；目标是连续牛熊检验，不能把2018—2023当成硬性限制。此次未运行第三方代码、未购买、未写生产。

## 实际取得数据

[teddykoker/survivorship-free-spy](https://github.com/teddykoker/survivorship-free-spy) commit `0bcc715e2dd37b7ecec65c549be843574120bd58` 的实际CSV已下载，原字节、SHA256、首末行和固定commit URL见 `tmp/github_history_routes_20261025/manifest.json`。共14个原缺口代码取得部分历史。

|代码|行数|首日|末日|
|---|---:|---|---|
|XLNX|1258|2013-02-28|2018-02-27|
|ALXN|1258|2013-02-28|2018-02-27|
|CELG|1257|2013-02-28|2018-02-27|
|CTXS|1258|2013-02-28|2018-02-27|
|CERN|1258|2013-02-28|2018-02-27|
|ESRX|985|2014-03-31|2018-02-27|
|CA|1258|2013-02-28|2018-02-27|
|MYL|1258|2013-02-28|2018-02-27|
|ATVI|626|2015-08-31|2018-02-27|
|ANSS|165|2017-06-30|2018-02-27|
|DISH|228|2017-03-31|2018-02-27|
|EA|1258|2013-02-28|2018-02-27|
|HOLX|481|2016-03-31|2018-02-27|
|WBA|794|2014-12-31|2018-02-27|

这些文件是S&P500历史成员截取后的OHLCV，不能直接代替Nasdaq100全生命周期数据。XLNX等为调整价，不带股息拆股字段；源代码/原WIKI需进一步核对，不能名义价格账本再重复调整。CELG行数少于同区间其他股票须检查缺日。仓库文件树未发现LICENSE，因此不重新分发原数据，不把公开可访问等同明确再分发授权。该路线已证明旧ticker免费日行情可以取得，但不覆盖完整2008或2020熊市。

## 优先的更长历史路线

[CEllis40/ml4t_data的WIKI状态文档](https://github.com/CEllis40/ml4t_data/blob/main/docs/wiki_prices_status.md) 提供实际归档入口 [Kaggle WIKI镜像](https://www.kaggle.com/datasets/marketneutral/quandl-wiki-prices-us-equites)。文档声称1962—2018、3199股票、含原始OHLC、股息、split_ratio与调整价。初次筛选时尚未下载；后续已取得并扫描完整归档，详见下方实测。作者声明不能替代历史Nasdaq成员分母核验。

## 已筛掉的路线

[Financial-Data-Project-in-Azure](https://github.com/cheukhin1024/Financial-Data-Project-in-Azure) README宣称XLNX 2005—2022与多个退市股，但网站标记删除，SFTP服务注明因成本不再提供，现入口需邮件邀请；公开文档中的凭据未使用，证据副本已脱敏。其OHLC为股息和拆股调整价、包含盘外交易。不能按免费直接下载可用处理。

[plotly/datasets](https://github.com/plotly/datasets/blob/master/all_stocks_5yr.csv) 文件树确有5年股票CSV，尚未下载；可能适合交叉核价，不作为完整牛熊主路线。

生产V27未改变；所有下载均未获准进入回测。下一步推荐完整WIKI归档覆盖审计，而不是停止研究或继续重试Yahoo旧ticker。

## 后续实测：完整WIKI归档已取得

一次公开metadata、一次download请求，无需注册或凭证。HTTP200，ZIP 463,184,323 bytes，SHA256 `adfd226694c6f3ec2c56b585d973764180a39a3ec516601721e90096dc1de94f`。实际成员文件是1,797,003,576 bytes的WIKI_PRICES.csv，非上述教程描述的Parquet。本地文件 `tmp/github_history_routes_20261025/wiki_archive.download`，下载清单 `kaggle_download_manifest.json`。

全文件流式扫描完成：15,389,314行，3199 ticker，1962-01-02—2018-03-27；字段含原始OHLCV、ex-dividend、split_ratio及adj_*。14个已下载GitHub样本全部在WIKI中有2007—2009各756行。XLNX历史始于1990-06-18；ALXN始于1996-02-28。全量按ticker范围和2007—2009行数见 `wiki_coverage.json`。

这解决了“真实取得长期退市证券行情归档”的缺口，尚未证明所有历史Nasdaq100成员完整、公司身份无误、交易日完整或价格单位正确。Kaggle metadata明确licenseName=Unknown；不发布原数据。下一步按历史成员分母核验2007—2009覆盖与2006训练预热，查缺失证券及企业事件后接入隔离研究账本，不能直接称牛熊回测完成。

## 外企/ADR候选补充实测

8条Yahoo公开请求各一次、无重试，ERIC/FLEX/INFY/LOGI/RYAAY/TEVA/TCOM/BB全部HTTP200，每个1034条非空OHLC，2006-12-01—2011-01-10。证据 `tmp/github_history_routes_20261025/yahoo_foreign_probe/manifest.json` 与各原始响应。ERIC返回4股息1拆股，INFY 8股息，RYAAY 1股息1拆股，TEVA 16股息，TCOM 2股息2拆股，BB 1拆股；FLEX/LOGI本区间事件为空。

这里只解决可下载候选覆盖：TCOM与BB仍须绑定历史ticker身份；所有Yahoo OHLC均标记调整单位未认证，不能直接合并原始名义价账本。查询区间之后的拆股/ADR比率也可能影响回填历史价格，因此本区间事件为空不等于历史OHLC已是名义单位。WIKI缺失不能一概视为退市股票缺失，外企/ADR来源覆盖差异是另一类原因。
