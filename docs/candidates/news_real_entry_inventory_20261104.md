# 现有新闻真实新买缺口库存（有界只读）

排除已反复使用的DLTR/PDD三案及所有合成空仓变体。本次只读取已有合同、预检及已保存摘要，没有外部下载、新模型或新回测。

|事件|新闻时间证据|原持仓/风险目标|既有经济结果已看过|可作为新买缺口试验|
|---|---|---|---|---|
|MRNA 2021-07-15纳入指数|原发布页19:01 ET，非历史初版认证|41/41|是，positive_three_arm与preopen probe|否，没有缺口|
|MRNA 2021-11-04财报|原发布页07:00 ET，现代归档|33/33|是，early_three_arm|否，没有缺口；原机械准入失败，经离线语义准入|
|NVDA 2024-08-28财报|既有asof_v2来源合同，仍需精确时点复核|96/96|是，asof_v2 run1|否，没有缺口|
|NVDA 2024-11-20财报|仅日期，public_available_at为空|85/85|是，economic_run1|否，缺口和精确时间均不满足|
|APP 2025-11-05财报|仅日期，published_at为空|2/2|是，economic_run1|否，缺口和精确时间均不满足|
|ENPH 2023-01-19|REJECTED_NO_VERIFIED_FRESH_TRIGGER|未准入，不计算|未形成准入回放|保留无有效新事件，不能凭大跌制造新闻|
|FTNT 2022-02-24|NOT_ADMITTED_NO_VERIFIED_TIMELY_FULL_BODY|未准入，不计算|未形成准入回放|保留证据不足/弃权，不强行运行|

本轮检查集合中可立即运行、既有原文和时间满足且真实策略有待买缺口的新增事件为0。不是全库或全市场不存在，而是这组已整理候选不具备。不能再用已持有案例或合成空仓宣称真实买入门控已验证。

最短下一步应改变选样顺序：先从连续基准账本提取真实BUY决策及前后事件日交集，再核查其事前公开原文；先锁住明确待买缺口，避免再次先找大涨跌新闻、最后发现全已持有。该步骤需另行限定数量与来源，不在本次库存里偷偷扩展下载或推理。任何已有收益被看过的样本只能作开发诊断，不能标记新留出样本。

证据路径：
- tmp/news_positive_preflight_20261028/preflight.json 与 news_positive_three_arm_20261028_v1/summary.json
- tmp/news_early_mrna_20211104_input_20261028/source_contract.json 与 news_early_three_arm_20261028_v1/summary.json
- tmp/news_nvda_20240828_two_open_20261028_asof_v2/initial_state.json
- tmp/news_cross_company_early_pm_20261028/{NVDA,APP}/source_contract.json、economic_run1/summary.json
- tmp/news_case_batch_20261029/sources/ENPH_20230119/source_contract.json
- tmp/news_five_case_sources_20261029/FTNT/source_contract.json
