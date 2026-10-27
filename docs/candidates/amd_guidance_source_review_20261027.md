# AMD 管理层收入指引原始来源复核（2026-10-27）

结论：已保存原文可明确比较**同一“full year 2022”收入指引**：26.3 billion ±300 million → 23.5 billion ±300 million，区间两端均下降。10月6日预告只谈第三季度初步业绩，所审全文没有年度收入范围或年度重申。数据已足以证明这两份文件的数字变化，尚不能宣称全渠道连续时序覆盖或直接成为实验准入事实。

本份独立审查仅离线读 `tmp/amd_guidance_source_20261027` 的四个 HTML/receipt，未联网或读取价格收益。主线程此前从官方站点获取了这些原文。

主线程已将两份全文中的 midpoint/tolerance 数字精确定位并保存 `numeric_facts.json`，分别换算为[26.0,26.6]与[23.2,23.8] billion。比较器新增显式“中值±绝对幅度”的单位换算校验，禁止将300 million当300 billion；11项数字比较测试及4项桥接测试通过。输出仍为 `SOURCE_BOUND_NUMERIC_FACTS_ONLY`，不是已准入事件。没有新增模型调用或经济回测。

## 数值与口径

| 原文件 | 官方定位/时间 | 可提取值及解释 |
|---|---|---|
| q2.html | [官方Q2结果](https://ir.amd.com/news-events/press-releases/detail/1084/amd-reports-second-quarter-2022-financial-results)，页首 Aug 02, 2022 4:05 pm EDT；Outlook全年段 | “full year 2022”；revenue；26.3 billion，±300 million；区间[26.0,26.6] billion。原文 continues to expect，属于延续此前年度预期，不是首次创设。 |
| preliminary.html | [官方预告](https://ir.amd.com/news-events/press-releases/detail/1093/amd-announces-preliminary-third-quarter-2022-financial-results)，Oct 06, 2022 4:17 pm EDT | 第三季度初步收入约5.6 billion，对比原Q3预期6.7 billion ±200 million。全文未找到full year或26.3/23.5；不能更新全年范围，也不能当全年重申。 |
| q3.html | [官方托管EX-99.1](https://ir.amd.com/financial-information/sec-filings/content/0000002488-22-000168/q32022991.htm)，标题/新闻稿日期 Nov 1, 2022；Current Outlook全年段 | 同一full year 2022；revenue；23.5 billion，±300 million；区间[23.2,23.8] billion。新上界23.8低于旧下界26.0，方向没有区间重叠歧义。 |

Q2 原文 `For NBSP the full year` 中含不换行空格；抽取必须先统一Unicode空白，不可因普通空格正则未匹配就记年度范围缺失。两段的non-GAAP修饰其后gross margin，不应直接套在收入字段上。未将年度同比增速或季度实际收入当修订指标。两份文件对同年收入的标题及量纲一致；这不是分析师一致预期surprise。

## 时间与索引绑定

[index.html 官方2022 Financial Releases列表](https://ir.amd.com/news-events/press-releases?category=financial&year=2022)列出：

- 2022-08-02 16:05 EDT = 20:05Z（Q2结果）。
- 2022-10-06 16:17 EDT = 20:17Z（Q3预告）。
- 2022-11-01 16:15 EDT = 20:15Z（Q3结果）。

11月1日仍为EDT，不能误转EST。索引标题链接为 `/news-events/press-releases/detail/1098/amd-reports-third-quarter-2022-financial-results`，而现存 q3.html 是同标题/同日期的SEC附件镜像。由此可记录“索引发布时间”，**尚未验证1098页面与已保存EX-99.1字节/正文等价，也未证明最早公开时间**。Q2和预告时间则在各自正文页直接出现。不要以2026抓取时间冒历史发布时间。

## USD 和财政年截止日

- 收入处都用 `$`，表格用`($M)`。原HTML全文搜索未发现明确 `USD`、`US$`、`U.S. dollars` 或 `United States dollars` 币种声明；美国公司与美国发布地点提供很强语境，但不是显式USD字段证据。**推荐保存 currency_symbol='$', currency_code=null, currency_status='CONTEXT_ONLY_UNCONFIRMED'**，在严格跨文件实验准入前绑定同发行人正式财务报表的USD计量依据。不要写“原文明确USD”。相同来源符号和量纲足以描述两点数值下降，不能据此静默完成币种门槛。
- 文件清楚写full year 2022，但本次没有取得明确年度期末日。保留 fiscal_year_label='2022', period_scope='FULL_YEAR', fiscal_end_date=null；不得从自然年或公司往年习惯猜2022-12-31。补正式年报/10-K的财政年度截止原始事实后才能填日期。

## 完整性复核

四份receipt均HTTP200，原始字节数与本次SHA256读回匹配：

| 文件 | bytes | SHA256 |
|---|---:|---|
| q2.html | 247170 | 824dcfcc9042e8f24de37b318f0f7316188d6f27f75ab7283a47012823784fe4 |
| q3.html | 333770 | 763dd09c6b2fca4ed0b6f3f3cf12f322416003c4f3dd8325b7cd5de22becfce1 |
| preliminary.html | 59920 | e2d1c28df6ac47744934c976c43528e37d1fa57558cca0ecc0e72cf064b83bb0 |
| index.html | 36436 | deca23b0b15c8292f788523cbe9ce3c2f3ff202d89aae266e9b41ee53866b459 |

索引显示8条2022 Financial Releases，本地HTML未找到分页链接。在8月2日至11月1日间只列10月6日预告，但列表是2026获取的财务分类快照，不覆盖全类别公告、SEC其他附件、电话会或其他公开渠道；不能据此证明期间没有任何年度指引更新。全文检查10月预告能排除“把该文Q3下修当全年下修”，不能替代全部渠道无修订证明。

## 下一准入缺口（最小）

1. 从发行人原财务报告绑定USD与FY2022期末日；此处不填猜值。
2. 核实索引1098公告正文与q3 EX-99.1对应关系，保留时间来源；准入若用SEC时间须另取实际acceptance，不能称最早发布。
3. 按冻结实验规则定义并核查时序覆盖范围，至少不能把10月文的年度沉默记REASSERT或NO_CHANGE；覆盖不足标UNKNOWN。
4. 在批准前仍是“已核实两点数字及一期中间预告”的来源审查，不是研究可用信号、不是收益证据。
