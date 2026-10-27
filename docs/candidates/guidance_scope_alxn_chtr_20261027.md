# ALXN / CHTR 全年收入指引适配检查（2026-10-27）

结论：本轮查到并核对两家公司持仓前最近常规财报及4月财报官方原文，**均未建立可比较的未来全年总收入数值指引对**。这只是所审文件的适配性结果，不是“公司所有渠道都不提供指引”，更不是中性或无风险信号。不能用已实现收入、同比变化、资本开支或合并预测替代。

范围：基准指定两股自2021-04-01起持仓；未用价格或收益筛样本。4次web调用封顶，仅引用SEC/发行人IR及发行人通过Business Wire直接发布的公告；未改规则，未扩公司。

| 股票 | 持仓前最近常规财报 | 4月财报 | 本轮可确认内容/适配状态 |
|---|---|---|---|
| ALXN | 2021-02-04，Fourth Quarter and Full Year 2020 Results；[SEC EX-99.1](https://www.sec.gov/Archives/edgar/data/899866/000089986621000009/earningsreleaseq42020.htm) | 2021-04-30，First Quarter 2021 Results；[发行人原始新闻稿](https://www.businesswire.com/news/home/20210430005085/en/Alexion-Reports-First-Quarter-2021-Results) | 前者给出2020已实现全年收入，后者给出2021Q1已实现收入；没有提取到未来FY2021总收入点值/区间，两文不能生成CUT/RAISE/REAFFIRM。 |
| CHTR | 2021-01-29，Fourth Quarter and Full Year 2020 Results；[公司IR原文](https://ir.charter.com/news-releases/news-release-details/charter-announces-fourth-quarter-and-full-year-2020-results/) | 2021-04-30，First Quarter 2021 Results；[公司IR原文](https://ir.charter.com/news-releases/news-release-details/charter-announces-first-quarter-2021-results/) | 已实现2020全年及2021Q1收入、客户经营数据，不是未来年度收入指引；检索未见guidance字段，所审正文未建立未来FY2021收入数值范围。不可把季收入乘4或同比增速外推为指引。 |

## ALXN 口径与来源局限

2月及4月公告包含药物临床试验进度、已实现收入/利润、并购事项；两文的Conference Call/Earnings Materials部分均明确因AstraZeneca收购协议不举行财报电话会。该事实只解释电话会安排，**不能据此推断撤回指引或完全停止指导**。4月稿的guidance一词命中的是监管机关对试验程序的指导，不能作为财务指引字段。

AstraZeneca并购材料中的长远营收目标/交易预测不是ALXN管理层独立未来全年总收入指导；本任务没有将其加入机制。仍缺其他同期投资者材料/合并文件的完整覆盖，状态应是 `NO_COMPARABLE_ANNUAL_REVENUE_PAIR_IN_REVIEWED_RELEASES`，全渠道是否存在指导保持UNKNOWN。

## CHTR 口径与来源局限

1月公告中的前瞻文字是经营战略、客户/收入/现金流增长方向，并非指定FY2021全年总收入范围；1月和4月财务表格分别是截至2020-12-31和2021-03-31的实际结果。仅看到表题Full Year Financial Results不能识别为Full Year Guidance。

4月文的expect等词也出现在通用前瞻免责段，不构成量化指引。电话会、配套幻灯片和其他事件未全面审查，因此只能说本轮原文没有形成可准入指引对，不能断言全年任何时点都不存在。

## 时间和下一步边界

上述日期来自原公告/官方标题；没有冻结最早发布时间、SEC精确acceptance及原始响应hash。CHTR先前官方日程公告计划1月29日07:00ET发稿，但预定时间不能直接当实际已核时间。ALXN的2021-04-30发布日来自发行人原稿来源记录，不能用它倒填4月1日信号。

这一检查已完成承诺的两股范围，不继续搜参或新增机制。对于原冻结“未来全年总收入下调”规则，两股目前只能记资料范围不适配/尚无可比较对，不能默认为NO_CUT。若覆盖率因此不足，应报告规则覆盖限制，而非改成AI利空或同比下降规则。
