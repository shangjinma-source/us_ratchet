# 754 会话的独立官方日历核验

结论：2020-12-31 至 2023-12-29，独立根据交易所官方休市表生成 **754 个日期**，与保存 AAPL 参考日期集合完全一致；缺失和多余日期均为 0。没有使用第二只股票作为独立日历。

本机 D:/python 与 Codex bundled Python 均未安装 exchange_calendars / pandas_market_calendars，没有安装新服务或库。采用标准库日期计算：周一至周五减去官方明确全日休市，半日市保留。

- 2021 用 [NYSE 2020-12-28 公告](https://s2.q4cdn.com/154085107/files/doc_news/NYSE-Group-Announces-2021-2022-and-2023-Holiday-and-Early-Closings-Calendar-2020.pdf)；PDF 实取 HTTP 200 并保存。
- 2022–2023 用 [NYSE 2021-12-27 更新公告](https://ir.theice.com/press/news-details/2021/NYSE-Group-Announces-2022-2023-and-2024-Holiday-and-Early-Closings-Calendar/default.aspx)，实际 HTML HTTP 200，包含新增 Juneteenth，不能沿用旧 2020 版表漏掉它。
- [Nasdaq ETA2021-45](https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2021-45) 明确 2021-06-18、06-21 正常开市；不因当年新增联邦假日误删股票交易日。

逐年计数：2020 区间内 1 日；2021 为 252；2022 为 251；2023 为 250。2021-12-31保留，2022-06-20/2023-06-19排除。2021-11-26、2022-11-25、2023-07-03、2023-11-24半日市保留。

产物在 `tmp/independent_calendar_review_20261026/`：`calendar_review.json`含实际差集、全部休市日期、特殊日期核验与版本；`official_session_dates.json`为独立生成日期；`sources.json`及原始文件保存来源 URL/HTTP/hash。未修改任何运行源文件或已绑定 hash 文件。

本轮没有穷尽搜索所有突发紧急休市历史公告；结果表明官方公开排定日历与实际参考集合不存在差异。仅核日期，不认证交易时段、夏令时开收盘时刻或资金结算日历。
