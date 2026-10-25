# 旧窗口来源覆盖的独立交易日历

根据 NYSE 于 2023-11-10 发布的 2024—2026 假期表逐年转录整日休市，加上 Nasdaq 于 2024-12-30 明确宣布的 2025-01-09 卡特悼念日闭市；2022—2023 部分复用此前已保存的官方日历审核。提前收盘仍作为交易日，不按整日休市处理。

2022-12-28 至 2026-07-30 共有 **899 个交易会话**，与旧窗口来源盘点所用 AAPL 参考日期逐项双向一致，缺失 0、额外 0、重复 0。此处使用 AAPL 仅用于对照日期，不用它替代个股收益或证明全市场当日没有个别停牌。

来源原 PDF、HTML 及哈希保存在 `tmp/old_window_official_calendar_20261026/`；结果为 `review.json`。独立重建入口 `scripts/review_old_window_official_calendar.py`。Yahoo 原参考文件使用 gzip 保存，读取时先解压，来源哈希仍绑定原始字节。

官方资料：[NYSE 三年假期公告](https://s2.q4cdn.com/154085107/files/doc_news/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar-2023.pdf)、[Nasdaq 特殊闭市公告](https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2024-87)。这是已声明假期及该项特殊闭市的核验，不冒充所有临时交易所通知的穷尽归档；未改变原回测日历或启动新经济回测。
