# FinRL 执行与风险层有限源码复核

核查日期：2026-11-04。固定提交 `4409abe925c904e570be78ebfb5e77ac3491dff8`。这是 AI4Finance-Foundation 的开源项目审查，不是大型金融机构实盘业绩认证。未下载模型、训练或运行收益回测，未改生产。

## 结论

不移植该版本 ExecutionManager/BacktestEngine 作为本工具交易执行层。止损、冷静期、限仓分层值得理解，但这些概念已有本地对应实现；目前没有证明其策略优于V27，不能只因项目知名度替换。

## 已读源码与验证

- [风险层](https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/strategies/adaptive_rotation/risk_manager.py)：读取完整模块。区分成本止损和峰值止损，冷静期用日历周；配置天数向上取整为周。它不等同于交易日冷静期，也不能直接解决本账户限仓卖出后反弹的偏好问题。未运行该风险模块。
- [执行层](https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/strategies/execution_engine.py)：读取完整模块，隔离提取并运行实际ExecutionManager类。generate_weight_matrix先逐日step，再用_compute_target_weights覆盖权重；后者采用月内第二个交易日/月末逻辑，没有沿用step的全部风控条件。
- [回测层](https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/backtest/backtest_engine.py)：重点核查run_backtest、数据预处理、策略构建与交易日对齐。权重在两处重新归一化，单股票20%会变100%，无法直接表达本工具保留现金的风险配置。代码片段没有建立新闻发布时间到首次可执行价格的合同；不能仅凭该入口认定历史新闻回测无前视。未运行bt回测，未审完整上游信号链。

## 有界反例

只用虚构TEST股票、2026-11-02至11-06五个交易日，禁止网络与下单；不是用户持仓模拟。

| 检查 | 逐日step结果 | 最终generate_weight_matrix结果 |
|---|---|---|
| 信号0、1、0、1、1；每日调仓、冷静期2日 | 0%、20%、0%、0%、20% | 0%、20%、20%、20%、20% |
| allow_short=False，第二日起负信号 | 本意为仅多头配置 | 最终连续输出-20% |

这证明所核查版本的这一入口有语义覆盖问题，不代表全仓所有策略均有同一缺陷，也不代表V27收益已经优于它。本地源码副本及结果：`tmp/finrl_execution_audit_20261104/`，不提交第三方源码。

## 对当前Goal的影响

1. 关闭直接引入该执行/回测链的分支，避免投入迁移和强化学习训练。
2. 可保留“按原因区分风险退出与配置调整”的设计原则；本工具已完成SNDK历史建议归因，卖4股来自50%限仓，不是20%退出。
3. 再入场候选仍须解决证券行动与价格单位证明、原子恢复和无关股票继续买入，不能用固定冷静期掩盖缺口。
4. 11月目标接口本轮只读确认已保存并引用当前提案；此事实不替代新部署盘中完整建议、真实成交和AI收益效果验收。
