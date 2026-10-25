# HONA / SPCX：旧窗口资格的有界补证

仅补资料，不修改 2021—2023 冻结研究、旧成员表或生产，不运行经济回测。证据及失败下载记录在 `tmp/hona_spcx_scope_review_20261026/`。

## HONA：成员未决，但训练短史已有确定处理

重新取得 NasdaqTrader `ECA2026-399` 原始 HTTP 200：HONAV 为 2026-06-15 开始的 when-issued，HONA regular-way 从 **2026-06-29** 开始，CUSIP **43849R105**。6/30 决策时仅有 6/29、6/30 两个常规交易会话，因此即使认定当时在 NDX，也不满足固定 253 日规则；可保留 `uncertain_members`，另明确“若属成员则合法短史排除”，不用把 242 格短缺继续当待下载行情。

这不是母公司连续改名：旧 HON 每股产生 1/2 HONA，母公司同时 1:2 反拆，HON CUSIP 438516106 → 438516205。HONA 不能继承 HON 价格来凑 253 日；实际已有 HON 的权益和反拆仍须独立记账。NasdaqTrader 是交易/公司行动通知，不是 NDX 成员通知。旧归档已指出同一缺口；本轮没有查得命名 HONA 的原始 NDX 加入/删除通知，保留未决，不能用 S&P 公告、当前 NDX 名单或通用分拆规则替代。

## SPCX：不应强求一进一出

现已读到 **Nasdaq, Inc. 自行发布的 GlobeNewswire 全文**：显示发布 **2026-06-26 20:00 ET**，明确 **2026-07-07 开盘前加入**，正文没有命名替换证券。该日期不是 URL 的 6/27，生效阶段也不再只是 DATE_KNOWN_ONLY。网页当前可读不等于拥有当时原始抓取存档；原始 HTTP 本次 403，保存的事实标为 web 工具观测。

官方当前 `Methodology_NDX.pdf` 第 3 页 Fast Entry 明确不要求删除另一证券，允许数量临时超过 100；官方方法更新说明确认 Fast Entry 改革于 2026-05-01 生效。因此 **102 本身不是缺少删除事件的证据**，不得为凑 101 假定某证券被删。建议将旧表 `remove:null` 的问题描述改为“公告未列删除，Fast Entry 无配对删除要求”，而不是必须寻找一个被替换证券。未认证当时完整旁侧事件流，不直接将全日删除集合伪认证为空。

原 May-1 特定版本 PDF 当前返回 404（两个官方域名均失败）；一般规则不能填造 HONA 特定事件。SPCX 加入晚于旧窗口最后一次 **2026-06-30** 决策，不改变该月候选集，也不应阻塞其训练编译；后续终点域仍保留新增 SPCX 及 HONA 不确定项，不强压数量。

来源：

- [NasdaqTrader HONA 公司行动](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-399)
- [Nasdaq 自发 SPCX 通知](https://www.globenewswire.com/news-release/2026/06/27/3318513/0/en/space-exploration-technologies-corporation-to-join-the-nasdaq-100-index-beginning-july-7-2026.html)
- [Nasdaq 当前 NDX 方法](https://indexes.nasdaq.com/docs/Methodology_NDX.pdf)
- [Nasdaq 2026 方法改革说明](https://www.nasdaq.com/newsroom/nasdaq100-index-methodology-update-why-now)

可消除的障碍：HONA 6/30 新股训练短史、SPCX 发布日期/时刻与有效阶段，以及错误的一进一出假设。仍未消除：HONA 命名 NDX 原始通知与当时可得性、历史完整事件穷尽性。
