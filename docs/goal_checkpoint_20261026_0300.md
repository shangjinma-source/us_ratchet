# 2026-10-26 03:00 截止交接

本文件在截止前保存；Goal 实际是否暂停，以 Goal 工具状态为准。用户要求到北京时间 03:00 左右即使未完成也暂停，等待醒来验收后恢复，不自动启动下一新闻 AI Goal。

## 可验收结论

**保持年化并降低最大回撤的目标尚未达成，待办不只剩开盘验收。** 完整 2021—2023 V27 连续基准已经独立复核，年化 -17.20%、最大收盘回撤 71.77%，期末仍未恢复前高。该结果不能被此前较短窗口的高年化替代。详见 [结果与图表](continuous_bull_bear_baseline_result_20261026.md)。固定 0.80 训练尾部门槛在 36 月均未改变选择，已停止，不追加阈值扫描。

截止前继续完成有意义的数据取得与整备，没有因时限删去失败证券、缩短冻结范围或将未知权益计为零：

| 已完成 | 实际边界 |
|---|---|
| 2024—2026 的 31 窗训练输入及独立重编译 | 3,127 个候选证券月份；六项短史排除、回溯身份和条件信号限制保留 |
| 名义 OHLC 及独立核验 | 124 个 ticker、647 会话、78,292 根实际报价；必要旧仓报价无缺日，来源争议保留 |
| 精确决策成本对齐 | 33 项微小表示差统一为已冻结执行 close，其余选股参数不变 |
| 连续输入结构预检及独立复核 | 129 个分日期证券身份、五处身份切换；没有调用经济组装器，没有新增经济回测 |
| SIRI 官方身份补证 | 旧股 10 换新股 1，法律实体和证券 ID 分开；零股现金金额和到账时间仍未知 |
| 不可覆盖的本地归档 | 每个 ZIP 条目实际读回验证；原资料未删除，原始行情和私人证据未上传 GitHub |

## 最新输入与复核入口

所有路径相对仓库根目录，原文件位于本机，不因文档链接而公开上传。

- `tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json`：SHA256 `32d7293282553d4c98daa161641663c0082da8f85b8b638974863f1ea8e951d3`。
- `tmp/old_window_execution_prices_20261026/execution_prices_v1.json`：SHA256 `3a0c0d3cc2b917a34c6f4328876dda50ee4cd8509af5c08e10fd86218729dfbf`。
- `tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json`：SHA256 `c1463e92169d9c32482fb86573cfe96f7d0f659405ff579a8038e56e45411f77`。
- `tmp/old_window_readiness_independent_20261026/`：v4 编译、OHLC、结构 v1/v2 的独立复核，最终状态 `PASS_SIRI_SUCCESSOR_INCREMENT_ONLY_ACTION_ASSEMBLY_STILL_BLOCKED`。
- [资料概览](old_window_data_preparation_20261026.md)、[独立复核](old_window_readiness_independent_review_20261026.md)、[归档与恢复](old_window_evidence_archive_20261026.md)。恢复最新资料使用 `old_window_execution_v4.zip` 加 `continuous_schema_delta_v2.zip`；已完成基准另见 [基准归档](research_archive_20261026.md)。
- [恢复审计与操作顺序](archive_resume_audit_20261026.md)：最新三项产物的直接 pinned 来源均已入包。分别保存两个同名清单；旧 binding 构建脚本硬编码原工作区，新目录不要重跑它，直接读取已保存 binding.json。尚未认证完整运行环境或跨平台执行。

## 用户恢复后的最短推进顺序

1. 沿实际选股及旧仓暴露处理股息、跨证券身份转换、分拆、并购和未到账权益；仅为实际触发的事件补齐执行与独立复核。七类未知行动及 dividends 仍为 null，不能传空数组伪称无事件。
2. 解决实际触发的执行缺口后，按 [有限运行方案](old_window_next_execution_plan_20261026.md) 冻结完整清单、预算与停止条件，运行单条 31 月连续 V27 基准。复用已审资料，不重做价格搜集，不启动参数网格。
3. 核验完整账本并解释收益来源，再依据已见缺陷和文献机制挑选有限候选。同口径保持或提高年化、改善回撤且无明显新增代价，才直接采用；有取舍时展示幅度。
4. 两个独立起始账户不得拼接成 2021—2026 连续回测。历史成员、回溯身份及训练信号的条件性不能改称完整时点认证或独立样本外。

当前复杂行动限制包括跨 SID 换股与零股、分拆子股、ANSS 开盘前现金加股票并购、WBA 未定值 DAP，以及 SIRI 合并后的零股现金。部分内核已有分支不等于独立 reviewer 已接通。详见 [行动接口检查](old_window_action_interface_readiness_20261026.md)。

## 生产与下一 Goal

本轮资料整备未改生产策略、账户、服务或定时任务。生产仍使用既有 V27 配置；不能宣称新的回撤优化已上线。真实盘中、用户成交、月底及新月验收保留在 [真实事件清单](real_event_acceptance_checklist.md)。

[新闻 AI 规划](next_goal_news_ai_plan_20261026.md) 仅作为下一 Goal 候选，尚未开发或影响买卖。先验证信息时间、噪音与增量价值，再考虑接入；不在本轮暂停后自行启动。
