# 本轮研究文件清单（news_economic_cases 所有）

提交选择应保留冻结版本，勿混入其他 agent 的生产候选。

- 固定价格代理：`pullback_execution_contract_20261105.md`、`pullback_daily_engine_20261105.py`；入口 `scripts/research/run_pullback_account_20261105.py`；7项测试 `tests/test_pullback_daily_engine_20261105.py`。
- 配对股息：`docs/candidates/pullback_dividends_20261105.py`；条件无行动：`pullback_absence_20261105.py`（DLTR/ON捕获）、`pullback_short_official_review_20261105.py`（ANSS）；早窗后续有限补证薄入口 `scripts/research/run_pullback_mxim_20261105.py`、`run_pullback_atvi_20261105.py`。
- 只读潜在暴露盘点：`scripts/research/inspect_pullback_potential_actions_20261105.py`、`inspect_pullback_staged_actions_20261105.py`。它们不是经济收益试验，未知行动处立即收束候选持有路径。
- 阶段代理：`docs/candidates/pullback_staged_contract_20261105.md`、`pullback_staged_engine_20261105.py`；后窗入口 `scripts/research/run_pullback_staged_20261105.py`，追加 `pullback_staged_dividends_20261105.py`、`pullback_staged_absence_20261105.py`；2项测试 `tests/test_pullback_staged_engine_20261105.py`。
- 阶段早窗入口与补证：`scripts/research/run_pullback_staged_early_20261105.py`、`docs/candidates/pullback_staged_early_supplement_20261105.py`（两条固定早窗已完整运行，现冻结）。

共享依赖：refresh 的 `docs/candidates/pullback_volume_filter_20261105.py`、`scripts/research/pullback_volume_inventory_20261105.py` 与其测试；root 的 `scripts/research/inspect_pullback_signal_volume_20261105.py` 和 `audit_pullback_result_20261105.py`。既有冻结 momentum prepare/action gate、exact fraction codec、股息账本、并购结算组件均复用且未改。

正式完成输出：`tmp/pullback_account_20261105/early_price_v7_all`、`late_price_v6_all`、`late_staged_price_v3`、`late_staged_volume_v3`。每目录 contract/source_hashes、execution_inputs、signals、book、summary 组成可复查闭包。早窗阶段完整输出 `early_staged_price_v1` 与 `early_staged_volume_v1`，均753会话。

原文与 web 观察在 `tmp/pullback_action_sources_20261105`；原行情/捕获与个人账本均只本地保留，不应盲目 git add tmp。研究脚本指向这些固定本地产物，仓库源码单独并不包含全部历史数据。所有真实账户、8010、生产策略未由本轮研究改写。
