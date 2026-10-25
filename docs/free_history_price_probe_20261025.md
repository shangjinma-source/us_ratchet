# 免费长历史行情：四类样本抽查

2026-10-25。一次4个Yahoo公开历史请求，范围2017-01-01至2024-01-01（结束日不含），另对XLNX做一次Stooq备用请求；没有重试、购买、注册或运行新收益回测。

| 样本 | 检查用途 | 实际返回 | 当前结论 |
|---|---|---|---|
| AAPL | 普通连续交易、拆股 | HTTP200，1760条非空OHLC，2017-01-03—2023-12-29，拆股事件1条 | 可取得候选数据；不等于原始名义成交单位已认证 |
| EBAY | 退出指数后仍交易 | HTTP200，同区间1760条非空OHLC | 行情覆盖退出日后的部分交易日；成员资格仍须按官方日期限制 |
| META | FB改名、ticker映射 | HTTP200，同区间1760条非空OHLC，返回symbol为META | 新ticker接口有改名前历史；需要保留历史ticker与证券身份映射 |
| XLNX | 并购退市 | Yahoo HTTP404，错误为No data found, symbol may be delisted；Stooq备用HTTPError | 此次未取得退市前行情；不能删除该股票或以AMD价格代替 |

1760是返回记录数，不是已独立验证的完整交易日历；本次检查只确认开高低收非空，未认证所有数据、股息与公司行动。备用请求错误未保留具体HTTP状态，不能把它误称为Stooq数据库确定没有XLNX，也不据此断言所有免费来源都没有退市行情。

## 官方日期与价格单位

- Nasdaq公告确认EBAY在2023-12-18开盘前退出指数。[官方年度调整公告](https://www.nasdaq.com/press-release/annual-changes-to-the-nasdaq-100-indexr-2023-12-08)
- Meta公告确认2022-06-09从FB更名META，CUSIP不变；现代ticker出现的更早历史不代表当时就叫META。[公司公告](https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx)
- Apple公告确认4:1拆股后于2020-08-31开始以调整后的单位交易。[公司公告](https://www.apple.com/uk/newsroom/2020/07/apple-reports-third-quarter-results/)

本次AAPL返回2020-08-28 Close约124.8075，2020-08-31 Open约127.58，同时列出8月31日4:1拆股。拆股前后价格量级连续，说明这组行情不能未经单位还原就当作逐日原始名义成交价；否则与账本拆股数量调整叠加会造成虚假收益。该判断是对本次响应和事件的核对，不是对所有Yahoo字段或所有证券的统一认证。

## 证据与下一步门槛

响应原字节及URL、时间范围、SHA256保存于`tmp/free_history_price_probe_20261025_v1/manifest.json`及`stooq_probe.json`，均标记`admitted_for_backtest=false`。行情原文不上传GitHub。

已有免费成员候选档案和部分长历史价格，但尚不具备完整2018—2023牛熊回测输入。后续必须形成全量历史成员分母、缺失证券清单、身份/公司行动映射和可检验的名义单位转换。此次抽查没有授权或触发全量无限抓取；不以当前存活股票子集替代完整策略证明。

生产V27及用户实盘验收安排不变。
