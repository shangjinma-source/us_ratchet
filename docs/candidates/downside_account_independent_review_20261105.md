# max10同次候选账户：独立审阅验收合同

审阅器：`scripts/research/review_downside_account_20261105.py --output <账户输出目录>`。不运行经济策略，不调用候选apply或整数风险helper；只接受COMPLETE，最终状态`INDEPENDENT_DOWNSIDE_MAX10_FINANCE_PASS`。

1. 独立解包`RESEARCH_EXACT_FRACTION_HEX_JSON_V1`，拒绝错误版本、非法hex与非正分母。校验完整contract源码/输入pins，固定20k、0佣金、5bp、36/31月、753/646日及终点。输出报告绑定审计代码、原财务checker、原frontier checker、账本、contract、所有月sidecar/decision/exposure文件。
2. 每月从冻结253收盘自行重建252日收益与QQQ同日原始收盘收益，核两源重叠及12个21日情景；严格使用分支真实资本。原金融checker另外核每次选择binding现金、持股、决策价和动态权益，不拿baseline资金替换。
3. 从同次保存frontier独立恢复原V27 cap50/rerank incumbent，再用原独立frontier checker核完整原评分/绑定。独立Fraction计算下行二阶矩及12情景财富乘积，核每个保留赢家整数股、发行人唯一、50%上限、实际≤10、现金/费用和风险资格。
4. 核sidecar精确摘要、资本/搜索/股票与QQQ坐标、研究源pins、阶段计数与超10过滤口径。incumbent合格时同分保留，仅严格产品提升可替换；不合格从合格保留篮子与现金按产品/低名义金额/字典序择优。
5. 原MonthlyExit风险、收盘→次开盘、实际整数成交、现金限制、股息除息应收与付款、逐日权益及回撤继续原财务独审。bounded股息逐项与已审原证据匹配，并检查窗口内全部已审股息未遗漏；不把仅gate准入视为实际入账。
6. 每月实际暴露gate必须admitted。ALXN/AZN复杂行动、SMCI持续正持仓身份迁移不在此脚本新增支持内：原checker拒绝即报告未通过，不删除行动或制造到账。零暴露仅复用已审严格证明，正暴露身份转换只允许原独审已支持的月初整数全卖路径。

小fixture三项已通过：版本codec、精确下行矩等号/超界、max10拒绝、保留原incumbent及错误最终目标拒绝；约0.04秒，没有账户经济回测。

限制：sidecar只保存每k赢家，没有全部已访问候选ledger。可独立核保留赢家可行性、分数、所保存域的最终选择与计数一致性，**不能独立证明它优于所有已访问且未保存候选**。原源条件性、非完整PIT/非OOS限制保持。审计通过不等于经济目标达成。
