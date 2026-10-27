# 管理层指引修订：两公司原始证据可行性

结论：PTON 可明确抽取同一 FY2022 总收入指引下调；NVDA 可抽取同一 FY2023 Q2 指引与期后初步业绩的下偏，但后者不是严格“未来全年指引修订”，不能混入同一机制。无需历史市场一致预期即可识别管理层自有数字变化，但仍不能证明提前卖出有效。

本轮按任务指定的 NVDA、PTON 两个策略历史出现股票查来源，未读取后续收益或按收益选事件；搜索目标含已知修订数字，属于结构可行性样本而非无偏事件样本。2次搜索查询+2个URL打开，总计4个请求操作，已停止网络。优先复用 PTON submissions 缓存；元数据与源hash另存 `management_guidance_source_check_20261027.json`。网页正文通过工具核实，尚未下载成独立原始响应，因此这份笔记不是可直接进入历史事件执行的已准入文件。

## PTON：同全年、同收入口径，明确下调

- 前公告：FY2022 Q1 股东信，SEC accession `0001639825-21-000320`，缓存 filing/report date 为 **2021-11-04**，acceptance **2021-11-04T20:02:01Z**。[SEC原始附件](https://www.sec.gov/Archives/edgar/data/1639825/000163982521000320/shareholderletter2022q1.htm)
- 后公告：FY2022 Q2 股东信，accession `0001639825-22-000007`，缓存 filing/report date **2022-02-08**，acceptance **2022-02-08T12:06:15Z**。[SEC原始附件](https://www.sec.gov/Archives/edgar/data/1639825/000163982522000007/shareholderletter2022q2.htm)、[公司IR同版股东信](https://investor.onepeloton.com/static-files/b0419d52-2795-4c38-a295-ae9c73550b8f)
- 定位：两文的 Updated Full FY2022 guidance，前文首页 Highlights / 后文 Full Fiscal Year Business Outlook。
- 结构记录：issuer=PTON/CIK1639825；period=FY2022全年；metric=total revenue；currency=USD；unit=billion；前range=[4.4,4.8]，后range=[3.7,3.8]。两端都下降，且后上界小于前下界，不需判断模糊措辞。不要把同页 Q2/Q3 单季收入混进全年范围。
- 可抽取性：文本可提取、可按表头+期间+指标绑定；先仅收入，不顺手纳入毛利率/Adjusted EBITDA，因为后文对重组费用口径另有说明。
- 时间边界：SEC acceptance 提供“至迟已公开”的可用时间，但不是最早新闻稿时间。不能声称两份就是所有中间修订中的相邻版本，也未排查中间预告；正式事件准入仍须完整按时序检查已发布修订，避免重复/过时比较。

## NVDA：同季度数字可比，但属于期后初步业绩

- 前公告：**2022-05-25** FY2023 Q1 results 的 Outlook。[公司原文](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-first-quarter-fiscal-2023)
- 后公告：**2022-08-08** FY2023 Q2 preliminary results，明确目标季度截至 **2022-07-31**。[公司原文](https://nvidianews.nvidia.com/news/nvidia-announces-preliminary-financial-resultsfor-second-quarter-fiscal-2023)
- 字段：issuer=NVDA；period=FY2023 Q2；metric=total revenue；USD billion；前point=8.10，tolerance=±2%，可确定区间[7.938,8.262]；后preliminary≈6.70。后公告自身明确回引 May revenue outlook 8.10，因此期/口径关联比简单拼两文可靠。
- 结论：是管理层自有预计业绩低于先前目标的原始事实，不是分析师 surprise，也不是YoY下降——后文同比仍增长。由于8月8日在季度结束后，只能标 PRELIMINARY_RESULT_BELOW_PRIOR_GUIDANCE，不能标仍在进行的全年指引 CUT。本次限定机制若只收未来全年指引，NVDA本例必须排除。
- 原文目前仅核到日期，未固定带时区发布时间，不可用日期猜盘前或盘后。

## 最小结构和下一步边界

每条需 issuer CIK/SID、来源URL与原始字节hash、公告可用时间与其类型、guidance期间起止/财年标签、scope=全年或季度、metric、GAAP/非GAAP口径、币种、倍率、range/point/tolerance、前后原句定位、是否仍在预测期、是否更正/撤回以及前后文来源绑定。区间重叠/口径变化/仅定性表述保留 UNKNOWN，不能让AI判减仓。

若继续，先将这一种全年收入区间比较做确定性离线抽取及人工核验，不能只收已知下调：必须同时记录不变、上调、缺失和不适用。上述2家公司不代表全窗口或实际暴露时都存在指引，更不能据此声称可回测。当前不新增交易规则，不跑收益，不扩至全市场。
