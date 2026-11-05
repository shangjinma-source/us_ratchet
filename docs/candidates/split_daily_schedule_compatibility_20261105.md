# 原资料定时任务拆股兼容边界（2026-11-05，只读核查）

实际 Windows `UsRatchet-DailySource-Evidence` 为 Ready，动作仍是 `run_local_dynamic_daily_sources_v5.ps1 -Execute`，配置 `research_contracts/daily_rss_recovery_20261022_v5/configuration.json`，hash `40ea7ba1078e4038c000bef8ea6a1d3b4b7da6f229460c587cb817546d9b4242`。未执行、修改或重注册任务。

仅替换 CLI 的 StrategyAccountStore 不足以兼容：

- `scripts/run_daily_dynamic_source_v5.py:58` 旧账本 reader 后，`data/strategy_daily_security_domain_v1.py:51` 再次调用旧 ledger replay；拆股事件仍拒绝。
- 同 domain 模块50–99行使用原月目标数量、原 unit_review 和 mark/training 绑定；不是实际保存的 frontier proposal 数量及新 native training/timing authority。不能直接接新账本而保持旧域。
- `data/strategy_daily_first_window_v3.py:187–210` 首窗口要求原收据闭盘重叠、close等于adjclose、无行动。`data/strategy_daily_sid_continuity_v1.py:69–80` 连续窗口同样拒绝行动、要求close等于adjclose、19日逐值相等；不是明确拆股坐标投影。
- `data/strategy_daily_security_domain_v1.py:168` 聚合仍调用旧 evidence rebind。不能把新原生 evidence 类型伪装成旧已审核 packet。
- `data/strategy_daily_dynamic_factory_v5.py:94–155,240–277` 维护逐日旧 configuration/hash/parent/aggregate/terminal 链；其 migration 只允许已固定旧新配置关系，不支持把新账本和新证据 schema 静默接到旧 run root。

最小可落地路线应复用已完成 ConfiguredNativeAdmission 的固定 target 授权、NativeCaptureReview 和实际采集/normalization，但为定时资料任务单独提供 source-only 构造入口（不调用 preview 生成行情订单，也不把写risk的完整 NativeMonthCaptureReader冒称只读资料采集）。其输出采用新 schema、新 runs root、明确切换会话与消费入口，保留旧 parent 历史。需同时绑定新账本重放、实际 proposal 域、原单位基线/三时点、新 source review、消费者；不能只补一个 reader。

本轮不创建未接通的 guard 或替换脚本。未核验真实未来券商证据，未修改原 pinned 源、配置、任务、真实库。检查范围为 launcher/CLI/factory v5 与 v4 比对、domain、first-window v3/v2、SID continuity；未扩至全面调度迁移。原未拆股运行链可继续保持，是否切换应由后续整体发布验证决定。
