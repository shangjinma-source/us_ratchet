# 财报机制相对 V27 的真实增量边界

本轮只读源码、既有输入结构与停止记录；未查询新资料、读取新候选未来收益、实现策略或调参。

## 当前实际信号，不宜笼统称“量价多因子”

|层|实际输入/规则|代码依据|
|---|---|---|
|月度价格训练|252个交易日跨度，每21日一个收盘价格比值，形成12个历史总增长因子；执行名义价格另作股数/资金计算|`backtest/return_priority_monthly_training_inputs.py:57–67`；`docs/recent_training_windows_preparation_20261026.md`|
|组合评分|每情景剩余现金＋各整数股初始名义金额×历史价格因子；最大化财富增长因子乘积（等价平均对数财富），不是未来收益预测|`scripts/audit_capped_training_frontier.py:evaluate`；`backtest/return_priority_fresh_cash_quantity_search_v2.py`|
|约束与搜索|真实分支可投资现金/持仓、整数股、费用/最低现金、发行人去重；8192原搜索预算，同次连续候选32步；并非财务指标打分|`data/current_research_capital_decision.py`；`backtest/continuous_guided_account_decision.py`|
|V27配置|单股投入上限1/2；同次已生成候选前沿在封顶后重新评分，严格改善才替换|`backtest/capped_frontier_rerank_research.py`|
|日级退出|月内收盘峰值回撤20%退出，月内锁定；新月重置；明确单位/公司行动|`core/monthly_peak_exit.py`；`backtest/monthly_exit_core_research_adapter.py`|
|生产执行|账户版本/目标绑定、保存前沿提案、实时证据与限价等执行约束，不等同次开盘研究模型|`data/saved_frontier_daily_composition_v1.py`；`data/saved_frontier_live_reader_v1.py`|

已核选股接口 `search_arguments` 为 prices/metadata/entered_cash/fee_bps/minimum_cash_buffer/training_scenarios/scenario_dates/decision_date/max_objective_evaluations/fixed_seed/quote_as_of/price_basis；metadata示例仅 ticker/issuer_id。未发现此评分路径输入成交量、EPS、收入、估值、分析师预期或公告情绪。因此“盈利信息已经包含在现有量价feature”不成立；“价格反应与价格信号经济含义重复”则成立。这里只说明现行已核路径，不能把仓库其他实验误算作上线feature。

## 与财报新机制重复到什么程度

盈利同比变化是新增数据维度，但不是 surprise。companyfacts能提供同申报可比季度事实，不能提供公告前市场预期；利润负值、业务剥离、重述、YTD及披露时点仍须门控。已有双surprise路线因可信历史预期不足而停止，不能换名用同比替代；见 `docs/candidates/news_mechanism_screen_20261027.md`、`scripts/extract_sec_quarter_events_v2.py`、`scripts/build_historical_sec_event_inventory_v1.py`。

财报后价格反应直接取价格，和12段价格因子、日级20%退出高度相关，但不是相同规则：原月度评分不按公告对齐，月中小于20%的下跌不会必然退出；事件条件能更早阻止一次原本会发生的补仓。单纯再加“跌了就卖”容易重复风险规则，不能宣称新增基本面能力。若原策略已经退出、没有待买缺口，新闻禁买当日没有增量；需要明确记录无动作而非挑另一日。

财报后上涨再买也可能只重现价格追随；必须等用于判断的完整收盘后再决策，不能既利用当天收盘确认又按当天开盘成交。事件跳空收益已经发生，不可算作新策略提前避免或赚得的收益。

## 现有可复用接口

- 事件：`scripts/research/extract_news_risk_facts_v1.py` 只提事实；`news_fact_rule_bridge_v1.py` 输出经来源审核的事件/拒绝。当前严格数字规则未准入；不是任何新闻机制都必须有旧数字。
- 价格/账户：两完整基准 `execution_inputs.json` 的 assembled.close_prices、ohlc、session_dates，配合 `tmp/news_session_clock_20261027/clock.json` 的真实开收盘时点；公司行动与价格坐标不能跳过。
- 原风险与订单：`backtest/guidance_news_risk_research_v1.py` 的 BLOCK_NEW_BUYS 可保留原退出；`backtest/guidance_frontier_research_v1.py` 接真实provider/风险；新机制必须独立规则版本，不沿用“交付延迟”事件名称。
- 局部因果初始化：`scripts/research/run_mrna_causal_local_v1.py` 展示恢复原风险状态、每日推进、月度选择只有实际分支账户和原输入完全一致才复用的方式。不同账户须独立重算或停止。`run_local_news_case_replay_v1.py` 的固定未来目标实验不能替代此流程。

## 最小值得先核查的增量（尚未注册或执行）

若继续财报方向，只考虑一个独立的“已认证财报事件＋公告后第一个完整交易日价格确认→暂缓该证券新增买入”诊断，先做动作交集而不优化参数：列出事件时点、首个完整交易日、当时原风险是否已退出、是否有正买入缺口。首可决策时没有正买入缺口，只能说明当日立即禁买没有增量，不能据此停止或否定持续事件状态路线。事件若持续至以后，仍可能阻止后续新买入（MRNA 的12/1路径已展示这种区别）。该后续交集须另有事前冻结的有效期与解除规则，不能为了触发改阈值或选择跌幅大的财报。

它有机会改变的是月中、原20%退出尚未生效、原目标仍要求买入时的入场时点；不是重写月度排名或自动清仓。当前缺口仍是固定确认条件、解除/到期条件、公告原文与可用时点集合，以及是否保留被取消买单预算。须在看候选之后收益之前一次性冻结，不能本文件自定任意阈值。先核交集可不调用新优化、不开发框架，也不需要假装拥有历史一致预期。已有26例 action_overlap 仅复用 SEC 接受后的首可决策时点，并非已认证财报首次发布时间后的完整交易日确认；未计算财报后价格确认，也未评估事件后续有效期内的新买入。

若用户坚持“盈利变化”而不是价格确认，先要求同口径原文与已知时点准入；已有同比双下降在已查账户交集中无触发，不应重复跑同筛选。事实获取、AI抽取通过、可执行订单变化和收益回撤改善是四层不同证据。当前没有新可采用策略结论。
