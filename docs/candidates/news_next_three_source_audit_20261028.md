# 固定接下来三例原文与时点审查（2026-10-28）

严格按计划审查MRNA 2021-07-16、08-03、08-09，没有换样、调用模型或做收益测试。三例均找到相关官方事实，但只有7月案例取得明确早于当日开盘的原分发时间；尚无一例证明新闻早于全部价格发现。原清单名义价格的条件性口径未在本轮重新认证，不能据此开展经济评价。

| 固定案例 | 已保存原文与时间 | 本轮结论 |
|---|---|---|
| 7/16 | S&P官网公告与PRNewswire完整原分发页均HTTP200；分发页标7/15 19:01 ET，说明7/21开盘前纳入S&P500、替换被收购的ALXN | 可归入前日盘后至当日开盘的已公开事件。19:01是该分发页面标记，不是已证明全球首发；不能按7/15收盘价假装买入，也不能把7/16全部涨幅算增量 |
| 8/3 | 公司官方托管PDF：mRNA-1345获FDA Fast Track；正文仅8/3日期。PDF创建字段13:19:42Z；正文链接BusinessWire本次不可访问 | 有真实事实，但公开分钟未认证，盘前准入弃权。创建时间不是公开时间；二手转载13:10UTC不能代替一手时钟 |
| 8/9 | 公司发行服务完整JSON，Business Wire via QuoteMedia，datetime=2021-08-09T10:05:00-04:00；澳大利亚临时批准18岁以上人群、预期9月交付。TGA官方网页可检索正文但仅日期；原HTML下载超时 | 公司稿在美股开盘后35分钟，不是盘前预警。政府宣布可能更早，但本轮没有认证分钟，不将当日涨幅归因或计为可捕捉收益；事前判断弃权 |

三种事实需分开理解：指数纳入可能改变被动配置需求，但不是营业利润预测；Fast Track只是加速开发/审评安排，不是上市批准、临床成功或确定销售；澳大利亚批准是实际监管进展，但已有采购安排不能再次当全新订单，计划交付也不等于已到账收入。这些可供后续投资复核，不能由已知上涨反推必然加仓。

本轮最值得保留的有限机制是“预先公告、未来生效的指数纳入”，其公告时间与生效时间清楚。仍须固定同类纳入但未大涨的对照，结合真实可得时钟和报价，再判断是否改善原策略；当前不创建交易规则。其余两例先保留原文和弃权时点，不继续找故事直到凑成正例。

直接来源：

- [S&P原公告](https://press.spglobal.com/2021-07-15-Moderna-Set-to-Join-S-P-500)
- [S&P原分发页及19:01 ET](https://www.prnewswire.com/news-releases/moderna-set-to-join-sp-500-301335329.html)
- [Moderna RSV Fast Track官方PDF](https://s29.q4cdn.com/435878511/files/doc_news/2021/08/03/moderna-receives-fda-fast-track-designation-respiratory.pdf)
- [PDF内BusinessWire原稿链接，本次不可访问](https://www.businesswire.com/news/home/20210803005702/en/)
- [澳大利亚TGA官方批准公告](https://www.tga.gov.au/news/media-releases/tga-provisionally-approves-modernas-covid-19-vaccine)
- [公司澳大利亚批准原分发JSON](https://www.accesswire.com/qm/data/getStory.json?storyId=6559149139936707&newslang=en)

检索入口次数分别2、3、2，另跟随PDF原文链接一次失败，未继续扩样或重试。4份成功原始响应及提取正文、1次超时记录、hash/采集时间在 `tmp/news_next_three_source_audit_20261028/receipts.json` 与 `audit.json`。没有历史采集日志、分钟级价格和不可改写原网页归档；当前取得完整原文不等于历史系统已及时收到。
