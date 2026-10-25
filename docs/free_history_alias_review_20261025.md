# 免费历史行情：五组旧代码检索关系

2026-10-25。本轮只核对五组明确改名线索，新增TCOM、GEN、WTW三个公开行情请求，无重试、无经济回测。未修改原成员表、旧响应或生产配置。

| 旧代码 | 查询代码 | 官方美股更名日期 | 证据与边界 |
|---|---|---|---|
| FB | META | 2022-06-09 | [Meta公告](https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx)明确CUSIP不变；复用已保存META行情 |
| PCLN | BKNG | 2018-02-27 | [Booking公告](https://www.bookingholdings.com/press-releases/the-priceline-group-inc-nasdaq-pcln-announces-name-change-to-booking-holdings-inc/)及[公司10-K](https://www.sec.gov/Archives/edgar/data/1075531/000107553118000015/pcln-20171231_10k.htm)确认交易代码变化；复用BKNG行情，拆股单位仍待核验 |
| CTRP | TCOM | 2019-11-05 | [公司提交SEC的公告](https://www.sec.gov/Archives/edgar/data/1269238/000119312519274119/d814130dex991.htm)及[存托凭证资料](https://depositaryreceipts.citi.com/adr/guides/pgm_d.aspx?cusip=22943F100&pageId=16&subPageId=151&typeDisplay=A)说明更名且CUSIP改变；不能简单当作永久ID不变 |
| NLOK | GEN | 2022-11-08 | [公司公告](https://newsroom.gendigital.com/2022-11-07-Introducing-Gen-The-Company-to-Power-Digital-Freedom)确认代码变化，无须股东操作；更早SYMC阶段及其他公司行动仍待独立核验 |
| WLTW | WTW | 2022-01-10 | [公司公告](https://investors.wtwco.com/news-releases/news-release-details/willis-towers-watson-announces-nasdaq-ticker-symbol-change-wltw)确认CUSIP不变，无须股东操作 |

此次TCOM、GEN、WTW各返回1760条非空OHLC，2017-01-03—2023-12-29。META、BKNG此前已返回相同日期区间。因此原25个失败旧代码中，五个现在已有明确查询路线；这是**代码检索缺口减少5项**，不是认证新增五家独立公司的完整历史。FB/META与PCLN/BKNG原本就在同一候选代码分母内，不能重复计数为新增公司。

仍未取得候选行情的20个代码：XLNX、ALXN、ANSS、ATVI、CA、CELG、CERN、CTXS、DISH、EA、ESRX、HOLX、MXIM、MYL、QRTEA、SGEN、SHPG、SPLK、WBA、WBD。

这里不将换股并购当作普通代码改名，不用收购方历史行情替代被收购方。CTRP资料还提示市场日期差异：维也纳交易所公告为11月8日，而本工具交易美国ADS，应采用美股对应日期，不能从不同市场公告直接抄日期。

## 留存与准入

三个新响应及SHA256：`tmp/free_history_alias_probe_20261025_v1/manifest.json`。原失败响应保留；所有新数据仍为`admitted_for_backtest=false`。正式数据准入尚需各证券身份与单位、历史成员日期、公司行动、缺日及253收盘预热检查。

本轮完成后不自动为20个剩余代码逐一猜测接续证券。退市历史仍是核心缺口，不能把可返回的存活证券组合成“完整牛熊策略回测”。
