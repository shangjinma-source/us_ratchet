# NVDA早期财报新闻资料就绪检查（2026-10-28）

已取得两份NVIDIA Newsroom完整业绩新闻正文及官方Q3 CFO评论。仅资料整备，未调用模型或回测。两篇新闻稿可按明确的发布日期假设准备开发输入；CFO没有独立发布日期，须另列时间假设敏感性材料，不能混用新闻稿的时间准入。

| 文稿 | 财季实际截至 | 新闻日期 | 正文规模 | 分发分钟证据 |
|---|---|---|---|---|
| FY2024 Q2 | 2023-07-30 | 2023-08-23 | 19,487字符 | GlobeNewswire发行页搜索结果为16:20 ET，即20:20 UTC；完整原响应403 |
| FY2024 Q3 | 2023-10-29 | 2023-11-21 | 17,666字符 | GlobeNewswire发行页搜索结果为16:20 ET，即21:20 UTC；完整原响应403 |

财年2024不等于日历2024。Newsroom保存的完整原稿只显示日期，不能把搜索结果时间冒充已保存全文中的已核字段。两稿所写17:00 ET是电话会时间，与16:20发布标签不同。分发服务当前标签也不能证明全球最早公开分钟或历史版本从未修改。若后续严格时钟准入要求完整可复核分钟，当前应等待补证而非自动填入16:20。

独立本地审查确认HTML可见日期与`PublishDate`标签一致，没有隐藏的分钟时间或可用发布时区。但无需无限追查分钟：若接受该标签代表实际当地发布日，并限定民用时区UTC−12至UTC+14，11/21发布日的最晚结束上界为11/22 12:00 UTC，加120秒处理延迟为12:02 UTC，仍早于当日美股14:30 UTC开盘。这个条件口径不假设美东发布时间，不套用SEC时刻，也不认证历史版本不可变；标记为`DATE_ONLY_CONSERVATIVE_GLOBAL_BOUND_CONDITIONAL`。实际历史发布时间不满足日期假设时，该结论不成立。

研究专用`news_date_only_bound_v1.py`提供该上界计算，6项边界测试通过，必须明确确认是发布日期标签，不能输入报告期日期。已有账户预检确认持仓/原风险目标均7股，原会话为11/21、11/22、11/24、11/27；两个有效开盘可为11/22和11/24，11/27到期，11/23不在交易会话中。无局部公司行动、分红、换月或未到账权益障碍。没有执行新的经济回放，现有价格单位仍保留条件性历史复原限制；11/24若使用收盘决策，必须另外遵守实际早收盘时间。

Q2原稿的下一季度收入展望为160亿美元±2%，针对FY2024 Q3；Q3实际收入181.2亿美元。可以陈述实际超过前次本公司对应季度展望上限，但不是市场共识意外。Q3原稿的200亿美元±2%针对FY2024 Q4，与前稿160亿美元不是同期间指引修订，不能直接认定上调25%。实际收入增长、利润率展望及产品进展均需与负面资料共同保留，不能只选风险句。

重要来源边界：本次两篇完整新闻稿未出现China/export restrictions/offset的具体讨论，稿内另外链接CFO commentary；该材料在初始预算内未取得，后续单独补充结果见下文。此前SEC报告中的出口管制及其他地区需求抵消内容不能倒填到这两篇早稿，也不能因早稿未写就认定出口风险不存在。下一实验若必须评估这一机制，应先明确需要单独CFO材料及其可得时间，否则只能检验两份新闻稿实际包含的事实。

原始来源：

- [NVIDIA FY2024 Q2](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2024)
- [NVIDIA FY2024 Q3](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2024)
- [Q2官方分发](https://www.globenewswire.com/news-release/2023/08/23/2730732/0/en/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2024.html)
- [Q3官方分发](https://www.globenewswire.com/news-release/2023/11/21/2784434/0/en/NVIDIA-Announces-Financial-Results-for-Third-Quarter-Fiscal-2024.html)

本地：`tmp/nvda_early_source_20261028/readiness.json`汇总路径、逐文件SHA、时钟不确定性；q2/q3.html、full_body.txt、receipt.json保存完整原文与提取。wire.html保存403拒绝页，只是失败证据，不当正文。已用4个检索query（2次web批调用）、4次原文请求，停止追加。没有价格、账户或后续收益分析。

## 独立追加：CFO直接链接定位（0新增请求）

在原四请求预算之外，按追加授权检查已保存Q3 HTML。CFO Commentary段实际仅链接 `https://investor.nvidia.com/home/default.aspx`，是IR首页，并非CFO文稿直链。故本轮未发起请求，未猜PDF地址或跟随旁链；没有把当前首页当历史附件原文。保存 `cfo_direct_link_check.json` 记录段落、精确href及原HTML hash。此前“链接CFO commentary”应精确理解为说明CFO材料在IR网站可得，不能解释为已经取得特定附件链接。出口/China/抵消内容和历史可得时刻仍未由这一步补证。

## 后续定向补充：完整CFO评论已取得

主代理另用1次官方定向搜索定位精确文件，本代理按新增授权只GET一次，HTTP200；不计入原4检索/4请求预算，无重试。取得[官方Q3FY24 CFO Commentary PDF](https://s201.q4cdn.com/141608511/files/doc_financials/Q3FY24/Q3FY24-CFO-Commentary.pdf)，8页完整提取，保存q3.cfo.pdf、pages.json、full_body.txt、receipt.json和review.json及逐文件SHA。此前“未取得CFO”的结论由本段更新；两篇原新闻本身仍未包含这些段落。

第2页明确：10/17宣布新的出口许可要求，10/23部分型号立即生效；并非11/21才发生管制。中国及其他受影响目的地中如今受管制产品的销售，在过去几个季度约占**Data Center收入20–25%**，不是总公司收入占比，更不是已实现损失比例。公司表示Q3收入未受重大影响，解释包括接近季末以及其他地区额外需求；预期Q4相关目的地销售显著下降，同时认为其他地区增长会超过这一下降。后者是公司预期，不是已经兑现的对冲，风险与抵消因素必须一起输入。不能套用运输延迟标签或仅凭这段认定永久损害。

日期边界：标题明确FY2024 Q3，PDF创建/修改元数据为2023-11-21 19:33:26 UTC，但这不是公开时间，文档正文未核到独立发布日期行。主代理提供的[11/1电话会预告](https://nvidianews.nvidia.com/news/nvidia-sets-conference-call-for-third-quarter-financial-results-6896799)表示将在11/21 17:00ET会前提供书面评论；承诺不等于实际交付证明，本步骤未另取该页。当前官方IR索引和PDF都不能证明历史16:20同时公开或版本不可变。若采用日期上界后次开盘的研究时钟，必须由独立准入明确其条件，不应把PDF生成分钟填作可交易时间。

## 独立复核结论与下一步边界

独立逐页复核与保存提取一致，语义检查通过；完整证据见本地`cfo_independent_review.json`。CFO实际公开时间仍为未知。不得对CFO调用日期上界工具并填`confirmed_publication_date_label=True`；新闻稿的日期标签也不能自动认证另一个附件。

若后续研究明确假设CFO在相关11/21业绩发布日已经可得，应使用独立质量标记`ASSUMED_ASSOCIATED_RELEASE_AVAILABILITY_SENSITIVITY_ONLY`，保留`confirmed_publication_date_label=false`和`public_available_at=null`，单独报告含CFO的条件敏感性结果，不能冒称通过原新闻稿时间准入。本轮没有启动该实验。

日期上界工具的6项边界测试已通过；之后仅整理代码格式与类型注解并再次通过相同测试。旧预检记录的源码hash保留原执行版本，不回写历史收据；后续运行需绑定当时的新源码hash。
