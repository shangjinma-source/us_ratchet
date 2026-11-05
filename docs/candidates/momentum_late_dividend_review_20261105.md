# 动量后窗普通股息补证

固定18个SID/除息日期，未扩大域；17笔已形成成对review_rows/dividend_events并经原append_ordinary_artifact验证。1笔明确待定，不进入执行数组。

- AVGO：2024-03-20与06-24名义每旧股$5.25；7月拆股后5笔使用$0.53/$0.59/$0.65。
- KLAC：2024-08-15 $1.45、11-18 $1.70、2025-11-17 $1.90、2026-05-18 $2.30。原公告计量均在2026年6月12日10:1之前；后期报表与provider的0.145/0.17/0.19/0.23为追溯单位，不能直接用于名义旧仓。
- GOOGL：ClassA，SID `security:0001652044:02079K305`；不是GOOG ClassC。
- 其余完成AMAT2026-05-21、GILD、INTC、MU、STX。支付日均有发行人公告/历史表支持，除息日单独核冻结provider；不由record日期替代。

待定：AMAT2024-08-22。发行人股息历史表明确列Ex-Date Aug21、Record Aug22、Payable Sep12、$0.40；冻结provider两来源为Aug22。追加有限官方/交易所搜索仍未取得直接消解该冲突的一手证据。保留金额/支付日事实，pending行独立保存，未给gate放行。可后续按交易所T+1规则和发行人公告核证；不能悄然忽略发行人表。

资料为官方网页/SEC/发行人PDF的工具解析观察及既有AVGO独审复用，明确不是HTTP原文字节归档。净税、托管费用、HSBC真实到账未证明；研究采用gross、发行人支付日会话收盘约定。补证不包含拆股执行或其他行动准入。

材料：`tmp/momentum_late_dividends_20261105/supplement.json`，SHA `f600f814402c89f785b1a3c6944a0b600bb1e8bd1a926307125bd635ab7c1cf7`；同目录`official_observations.json`含逐笔来源。
