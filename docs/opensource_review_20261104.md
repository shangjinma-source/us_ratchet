# 美股开源项目筛选与有限对照计划

核查日期：2026-11-04。状态：源码筛选完成第一轮，尚未证明任何候选优于 V27，未改生产策略。

## 筛选原则

优先大机构及专业团队近期项目，但以适配性、可核验源码和账户结果判断。通用预测精度、论文收益、机构名气都不能替代本工具的牛熊对照。只吸收有增量价值的模块，不迁移整套框架。保留真实账户、服务及原金融任务。

## 已核查项目

| 项目 | 本轮核查范围 | 可借鉴点 | 决定与限制 |
| --- | --- | --- | --- |
| [Microsoft Qlib](https://github.com/microsoft/qlib/blob/main/qlib/contrib/strategy/signal_strategy.py) | README及 TopkDropoutStrategy 源码70–210行 | n_drop 限制替换数量、hold_thresh 持有门槛、使用前一交易步信号 | 优先研究降低换手机制；不可直接复制其市场涨跌停假设，也不能以持有门槛阻止重大风险退出 |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean/blob/master/Algorithm.Framework/Risk/MaximumDrawdownPercentPerSecurity.py) | 单股风险模块完整源码 | 风险层独立生成目标持仓 | 该模块实际按未实现盈亏比例触发清仓，不是从历史最高净值计算组合回撤。默认5%不是适合本账户的证据，不照搬 |
| [FinRL / FinRL-X](https://github.com/AI4Finance-Foundation/FinRL-Trading) | FinRL README及新框架 README前100行、目录入口 | 选股、配置、择时、风险覆盖分层，目标权重作为接口 | 值得继续核查风险层与回测时序源码；README描述不等于已实现验证，不优先投入大规模强化学习训练 |
| [Google TimesFM](https://github.com/google-research/timesfm) | README前90行 | 通用时序预测与协变量 | 暂低优先级，非现成美股策略；还需核对权重许可及训练数据时间覆盖，不能直接把历史预测当无泄漏回测 |
| [Amazon Chronos](https://github.com/amazon-science/chronos-forecasting) | README前95行 | 概率预测及外生变量 | 暂低优先级；通用预测基准优势并不证明收益或回撤优势，先不下载训练模型 |
| [ZenTrade](https://github.com/wuyangfan234/zentrade) | 1321项目录树及下列6个模块 | 财报事件窗口、新闻观察记录、页面聚合、任务进度 | 仅取局部机制；其新闻模块仍是影子观察，不能当作有效交易机制。固定7日持有与强制减半不直接采用 |
| [EdgarTools](https://github.com/dgunning/edgartools) | README前160行 | SEC报告结构化提取与最新披露入口 | 继续核查时间字段；SEC接收时间不必然是消息首次公开时间，也不能补全所有历史新闻 |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | README前160行 | 结构化证据、反证、账户相关风险意见 | 不复制长链讨论；须进一步审计回测时序，尚无本账户收益证据 |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | README前160行 | 来源追踪、确定性计算与模型解释分离 | 不把长报告展示当成及时交易介入 |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | README前160行 | 事件驱动执行、回测与实盘语义 | 不引入重型重写，不具备直接接入汇丰账户的已验证方案 |

未完成：OpenBB旧仓库入口返回重定向，未完成新入口核验，不形成推荐。上述均非全仓逐行审计。

ZenTrade核查固定提交：dd9ea3ee3e7197044f858816daed5e2c514ffd10。已读 earnings_guard.py、news_shadow.py、strategy_cache.py、heavy_job_limiter.py、frontend/src/components/opportunities/useOppPage.ts、docs/architecture.md。新闻观察组间差异不能替代同一事件下两种动作的账户反事实对照；展示缓存不能复用过期挂单；任务限流代码为进程内实现。

## 下一轮有限实验

先修复实际建议刷新性能，再进入策略对照；保持 V27 为基线。

1. 减少无意义调仓：区分卖出原因（止损、持仓上限、排名换股、现金变化），先核对用户 SNDK 案例究竟属于哪一种。只设计一个持仓保留/替换缓冲候选及一个小额再平衡缓冲候选，不把所有卖出都归为追涨杀跌。
2. 新闻风险：只使用已能确认决策前公开的资料，比较事件窗口暂缓新买入与明确负面证据限制买入两种机制。分别规定何时解除、如何恢复买入；持仓减仓须另行明确规则，不自动由利空推导清仓。
3. 先分别测，再测最有依据的组合，不做全参数网格。参数、样本分段及淘汰条件在运行前写入清单。已有牛熊行情只支撑行情覆盖，新闻缺口仍单列。
4. 每项报告年化、最大回撤、最差阶段、换手、交易次数、错失上涨及错误退出后的反弹。统一股息/公司行动、整数股、现金及执行时点。把佣金敏感性与策略能力分开，零佣金不等于零价差或零滑点。
5. 事件案例可以检验链路和及时性；不能把事后挑出的暴涨暴跌案例收益宣称为全市场策略收益。保留按时间划分的未调参检验段，披露样本不足。
6. 无稳定增益就明确淘汰并结束该分支；若收益下降而回撤改善，展示交换幅度，不能按全面胜出自动部署。只有证据充分且符合用户已授权的全面改善条件，才进入部署验收。

## 工程落地边界

本地R58记录显示月目标读取约20秒，纯编译复用仅节省约0.196秒，已否决；报价已有并发。优先优化重复历史发布核验及建议后的等待，同时保持文件完整性、账户版本、目标、报价有效期的一致性检查。聚合页面与进度提示可参考 ZenTrade，但不能用旧建议缓存掩盖刷新失败。

本报告是筛选结果与待执行清单，不是已完成回测、已证明盈利或已部署的声明。
