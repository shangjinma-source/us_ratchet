# WBD 免费归档实际补齐候选

结论：已取得覆盖 2020–2023 的完整原 OHLC 实物，2022–2023 缺口不再仅有链接线索。尚未独立完成前身身份/名义单位锚点审计，不宣称经济主账准入。

来源：<https://zenodo.org/records/12566468>，标题 `Dataset: Warner Bros. Discovery, Inc. (WBD) Stock Performance`。公开 API 查询返回明确单文件 `WBD_stock_data.csv`，从该记录实际 `files[].links.self` 下载 HTTP 200，529,286 bytes。

- 官方 MD5 `13be07ed15743ef7a226d539aeb9c70a` 与本地完全相同。
- SHA256 `36efd7f62ae494f793f270cdbd784cda19b7a82b03dbfad93450b9a8f0bc5d03`。
- 全文件 4,774 行，2005-07-08 至 2024-06-26。
- 2020-01-02 至 2023-12-29 共 1,006 日，原 Open/High/Low/Close 全部正值、有限、低高价包含开收盘；重复 0、缺失 0，2020 预热 253 日。
- 日期参考为已存 AAPL Yahoo 时间戳，不是独立交易所日历。仅用原 OHLC，忽略 Adj Close/Volume。

关键名义价样本：2020-12-31 Close 30.0900001526；2022-04-08 Close 24.4300003052；2022-04-11 Open 24.0799999237 / Close 24.7800006866；2023-12-29 Close 11.3800001144。

下载文件自身把较早前身行情列在 WBD 名下，不能把文件标签直接当作历史证券身份。主线程已取得 DISCA→WBD 1:1 官方承接证据，实际接入必须使用该版本化身份映射。当前 QQQ 2020-12-31 本地锚点表未找到 Discovery 条目，因而本子任务没有虚构 SEC 单位锚点通过；后续需要对应前身名义价或重叠序列复核。

本批最多三条具体路线：Zenodo 关键词 API 命中上述实物；TickerLake 公开 GitHub 树只有成员 CSV、无已提交行情文件；financial-markets 的 master 树 HTTP 404。找到有效实物后停止，无扩大版本/重试被限流接口/经济搜索。

证据目录：`tmp/wbd_routes_20261026/`。`zenodo.json` 保留官方文件元信息；`WBD_stock_data.csv` 是原始实物；`wbd_price_audit.json` 包含 checksum、日期和 OHLC 校验及关键样本。首次本地解析误写编码别名 `utf8-sig`，随即修为 `utf-8-sig`，只重读已下载本地文件，未重复网络下载。
