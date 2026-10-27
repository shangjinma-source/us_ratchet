# PTON FY2022 收入指引时序核查（2026-10-27）

结论：2022-01-20 预告只披露已经结束的 FY2022 Q2 初步业绩，**没有在所审正文中重申、撤回或修订 FY2022 全年收入范围**。因此不能把约11.4亿美元与全年44–48亿美元比较，也不能把没有提及全年指引标成 REAFFIRMED。2021-11-04 与 2022-02-08 的全年范围仍是已核实的两点；本轮没有证明期间全部公开渠道覆盖，也不能证明它们是相邻有效版本。

本轮严格4次 web 调用，无403下载重试、无股价/收益读取、无模型调用。检索意外返回含行情标题的结果未用于判断或选择事件。仅新增本文件。

## 可追溯时间线

| 时间/依据 | 文件及实质内容 | 全年收入指引状态 |
|---|---|---|
| 2021-11-04；缓存SEC acceptance 20:02:01Z | [FY2022 Q1 原始股东信](https://www.sec.gov/Archives/edgar/data/1639825/000163982521000320/shareholderletter2022q1.htm)，已由上一轮核实 Updated Full FY2022 guidance | USD44–48亿；基准观察，不等于当时市场预期 |
| 2021-11-16发行事项；11-18 SEC acceptance 21:31:05Z | [8-K 0001193125-21-333887](https://www.sec.gov/Archives/edgar/data/1639825/000119312521333887/d265095d8k.htm)，本轮打开，正文Item8.01为股份发行；引述11-16/18 prospectus | 所读正文未见全年收入修订；未打开招股附件，不能证明附件无重申 |
| 2021-12-07股东大会；12-09 acceptance 21:32:21Z | [8-K 0001639825-21-000345](https://www.sec.gov/Archives/edgar/data/1639825/000163982521000345/pton-20211207.htm)，本轮打开，Item5.07股东投票 | 所读内容非收入指引，不作为更新 |
| 2021-12-10信贷修订；12-13 acceptance 21:31:37Z | [8-K 0001639825-21-000354](https://www.sec.gov/Archives/edgar/data/1639825/000163982521000354/pton-20211210.htm)，本轮打开，Item1.01循环信贷安排 | 所读内容非收入指引；未遍历信贷附件 |
| 2022-01-18 16:05 EST，官方搜索结果时间 | [财报日程公告](https://investor.onepeloton.com/news-releases/news-release-details/peloton-interactive-inc-announces-second-quarter-fiscal-2022/) | 计划2月8日盘后公布，不是全年数值指引；此日程后来改变，不能据它推定实际公布时间 |
| **2022-01-20 18:17 EST = 23:17Z**，公司正文明确时间 | [公司预告全文](https://investor.onepeloton.com/news-releases/news-release-details/peloton-interactive-inc-reports-preliminary-second-quarter/)；[SEC镜像](https://www.sec.gov/Archives/edgar/data/1639825/000163982522000005/pressreleasedatedjanuary20.htm)（搜索核实）；缓存对应8-K acceptance为2022-01-21 00:44:58Z | **FY2022 Q2初步收入约11.4亿，比较的是同季度原11–12亿指引；未提供全年范围** |
| 2022-02-08；缓存8-K acceptance 12:06:15Z | [FY2022 Q2 原始股东信](https://www.sec.gov/Archives/edgar/data/1639825/000163982522000007/shareholderletter2022q2.htm)，前轮核实、本轮官方搜索再次返回 | FY2022全年收入37–38亿；与已知44–48亿两端均下降 |

## 1月预告的原文定位及判断

公司页面全文从标题、财务要点、会议安排、Financial Disclosure Advisory 至附表均已读。本页唯一短引文：

> “Total Revenue of approximately $1.14 billion”

标题和正文将该数字明确限定于截至2021-12-31的第二财季。要点同时给出原季度区间11–12亿美元；不是全年44–48亿美元。管理层讲成本调整，并把进一步说明留到2月8日；全文没有新的全年收入数值，也没有明确确认全年目标不变。附表收入为1138百万，是同季度较精细的初步数，不能当另一条指引修订。此网页有18:17 EST时间，比SEC接收时间早，研究必须保留两者，不能把SEC时间叫首次公开时间。

建议仅建立 `PRELIMINARY_QUARTER_RESULT / annual_guidance_action=NOT_STATED_IN_REVIEWED_DOCUMENT`，不可生成年度CUT或REAFFIRM事件。未发生某类事件的断言范围只限该文，不外推到整段时间。

## 覆盖清单和剩余缺口

本地只读来源为 `tmp/historical_sec_gap_fetch_20261027/PTON.submissions.json`。其中区间内8-K/10-Q共9项：

- 2021-11-04 8-K 0001639825-21-000320；11-05 filing/11-04 acceptance 的10-Q 0001639825-21-000322。
- 2021-11-18 8-K 0001193125-21-333887。
- 2021-12-09 8-K 0001639825-21-000345；12-13 8-K 0001639825-21-000354。
- 2022-01-21 8-K 0001639825-22-000005（1月20日预告）。
- 2022-02-08 8-K 0001639825-22-000007；10-Q 0001639825-22-000013；8-K 0001639825-22-000014（21:18:04Z，晚于早间股东信）。

这只是缓存索引的8-K/10-Q范围清单。未完整遍历招股书/电话会/管理层公开活动/全部附件/公司博客；搜索未发现另一份年度范围公告不等于不存在。新网页未保存可独立复验的原始字节和hash，引用可追溯但尚非已冻结实验输入。因此仍保留 `chronology_coverage=INCOMPLETE`，不得将完整无中间修订作为已通过的门槛。原指导实验如何处理此缺口需主线程按冻结规则决定，本任务不放宽准入或修改交易规则。
