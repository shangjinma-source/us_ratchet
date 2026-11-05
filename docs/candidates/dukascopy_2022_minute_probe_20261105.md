# 2022 美股分钟数据：Dukascopy 单日真实探针

2026-11-05，仅一个证券日、一次行情 HTTP 请求；无认证、注册、付费或回测。先查本库，既有 Ross 调查只落实 Yahoo 常规时段近端分钟和 Alpaca 需认证；没有已否决 Dukascopy 的记录。本轮不再检查 Alpaca。

## 结论

**已实际取得 2022 年的美股标的分钟 BID 报价，免费免认证路径成立；不是全市场成交 OHLCV，不能直接填补 Martin 的真实成交量确认，更不能充当 Ross 盘前逐笔。** 可以支持下一步有限的“分钟报价形态/触发时序代理”检查，尚未具备真实成交回测准入。本轮到此收束，不扩股票或日期。

## 固定样本及实际结果

先定 AAPL（现有 Nasdaq 大盘研究域中的证券）、2022 首个交易日 1 月 3 日；未按事后涨跌挑日。2022 是熊市年份，这一个日期不是牛熊覆盖或策略收益证据。

- URL：`https://jetta.dukascopy.com/v1/candles/minute/AAPL.US-USD/BID/2022/1/3`
- HTTP 200，9023 字节；一次行情请求，无 Cookie/token/API key；仅普通 User-Agent 与公开历史导出页 Referer。
- 原文 SHA256：`af72f795083b76582b3bcdc460eed3e5a1f8e66d82be5d522a4ceee26fdbae5f`。
- 390 条实际原始记录，UTC 14:30–20:59 / America/New_York 09:30–15:59（EST），连续无缺分钟，OHLC 高低关系通过。
- 盘前 0 条、盘后 0 条；不能用这个样本推断其他股票所有日期绝无盘前，也不能说已获得盘前覆盖。
- 首分钟 O/H/L/C：177.826 / 178.166 / 177.696 / 178.046；末分钟：181.847 / 181.977 / 181.776 / 181.927。
- raw volume 首分钟 3.12、末分钟 3.135。保留字段名 `provider_quote_volume_raw`，**不命名成交股数**。

## 来源性质及不能偷换的边界

[Dukascopy 官方 FAQ](https://www.dukascopy.com/swiss/english/about/faq/?c=658c629fd6012) Historical Price Feed 栏说明分钟量来自 best bid/ask 对应量的期间加总，并非交易所成交量；历史保留最优 bid/ask，不是历史 L2。[官方 CFD 市场目录](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/) 可定位 AAPL.US/USD。故它是该提供商股票 CFD/报价侧数据，不是美国 SIP 成交带，也不证明汇丰账户可按该报价成交。

本次仅取 BID；ASK、实际 spread、成交条件码、撮合次序均未验证。不能用 BID 直接当买入成交价或把一分钟内触及高点推成限价必然成交。

复权与股息处理未获此接口的完整历史单位认证。不能因价格看似正常就宣布名义、前复权或总收益口径；跨拆股/股息日期必须另核，不能与现有日线直接按 ticker 拼接。当前证券目录也不证明 2022 当时完整候选域、退市证券覆盖或无幸存者偏差。

## 可复核实现

API 格式、AAPL instrument code 以及解码算法来自[项目作者源码](https://github.com/Leo4815162342/dukascopy-node)，本次查到 commit `068bf57b67e3cae3f5c952653ef20157d3852699`；正常化源码按该 commit 获取。本地只实现累加时间/价格 delta 的离线解析，没有安装包或执行该项目代码。

关键：上游 normaliseCandles 会在缺口前补平线。本探针 **不补任何平线**，只解码原始 `times` 对应的实际记录，避免制造凌晨行情；390 条均来自原响应。

证据：`tmp/dukascopy_minute_probe_20261105/receipt.json`、`aapl_20220103_bid.response`、`decoded_actual_rows.json`、`checks.json`，以及已保存官方 HTML/收据和下载器源文件。离线复核：

```powershell
D:/python/python.exe -m scripts.research.check_dukascopy_minute_probe_20261105
```

若下一步继续，最小范围是预先固定有限日期，同证券同日取得 ASK 并检查双边一致性/单位，再把已有日线筛选与分钟报价触发分开对照；分钟成交量仍缺，必须明确省略该机制而不声称完整 Martin 复现。此来源当前不适合 Ross 盘前真实量/逐笔方案。没有新增经济回测或收益声明。
