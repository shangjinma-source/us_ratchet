# 有限开源机制核查：分散与跨月保护（2026-11-05）

本轮先读opensource_review_20261104.md，避免重读已核Qlib TopkDropout、Lean未实现盈亏止损和ZenTrade新闻影子模块。随后仅通过GitHub connector读取2个官方项目的实际实现，不启动回测或改生产。

## A：四股等金额分散

[LEAN EqualWeightingPortfolioConstructionModel.determine_target_percent](https://github.com/QuantConnect/Lean/blob/master/Algorithm.Framework/Portfolio/EqualWeightingPortfolioConstructionModel.py)按有效非FLAT信号数N生成1/N权重，默认支持多空且日度再平衡。本工具只借等资金预算，不照搬日频或做空，不要求引入LEAN。

可执行固定对照：沿原已冻结排序选4只（当期合格不足4则明确按预登记规则处理），每只25%资金预算、整数股向下取整余款留现金；与V27采用完全相同次日执行/已用现金/公司行动/费用口径。四股可以仍高度相关，不等于四个独立风险来源；必须报告行业/相关性集中和QQQ对照，不能只看交易减少。

[LEAN RiskParityPortfolioOptimizer.optimize](https://github.com/QuantConnect/Lean/blob/master/Algorithm.Framework/Portfolio/RiskParityPortfolioOptimizer.py)以协方差和log风险预算目标求权重，失败回退等权。实际Newton-CG没有显式约束，之后clip但未再归一；不能直接复制并假定上下界和总权重均成立。现有日行情可算同期收益协方差，但拆股口径和缺失交易日必须先统一。当前先跑等额A，不同时新增风险平价参数搜索。

## B：跨月盈利保护

[LEAN TrailingStopRiskManagementModel.manage_risk](https://github.com/QuantConnect/Lean/blob/master/Algorithm.Framework/Risk/TrailingStopRiskManagementModel.py)保存持仓侧和持仓绝对价值峰值；并不每月重置，未持有或方向变化会重置，阈值触发输出0目标并取消旧insights。

可借持仓生命周期持续风险状态，避免自然换月清空峰值；不能照搬默认5%。其用持仓总价值而非单位价格，加减仓本身会改变比较基准；本工具应使用公司行动一致的每股/单位收益峰值或显式重基，现金入出不能制造价格回撤。用户看好目标价也不能变成事后设阈值。B先沿用冻结退出阈值，只改变跨月状态重置规则，完全退出后重置，再入场规则不夹带变更；这是本地候选定义，并非LEAN原样提供的赚钱策略。

## Qlib：基准风险预算的参考边界

[EnhancedIndexingOptimizer.__call__](https://github.com/microsoft/qlib/blob/main/qlib/contrib/strategy/optimizer/enhanced_indexing.py)优化预期超额收益减跟踪风险，约束个股/因子偏离及总换手。它优化跟踪误差，不是最大回撤；满仓约束也不等于适合本账户现金需求。失败后会尝试移除换手约束，不能把原delta视作始终成立的硬限。现有数据缺完整历史QQQ权重及因子暴露，不直接上增强指数优化器；可借鉴先明确定义对QQQ的收益与回撤判据，保留现金和失败状态。

## 许可与判定

LEAN上述文件明确Apache-2.0；Qlib文件及[LICENSE](https://github.com/microsoft/qlib/blob/main/LICENSE)明确MIT。复制实现需保留对应许可/版权声明；仅吸收规则并不需要迁移框架。

优先顺序：A等额分散、B跨月保护独立固定对照；二者均完成后才决定是否组合。胜出必须以同窗口同资金口径的年化>QQQ且最大回撤<QQQ为用户目标，并逐窗报告；样本内改善不构成未来保证。既有资料覆盖限制继续披露。项目名、星数、默认参数不构成收益证据。
