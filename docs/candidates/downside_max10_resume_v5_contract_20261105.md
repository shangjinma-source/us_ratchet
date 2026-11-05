# Downside max10 v5：LRCX证据配置续接

新小入口 `run_downside_account_candidate_20261105_v5.py` 私有加载原v3实现，仅使用v5 freeze读取器；不复制大runner、不改v1–v4或原经济规则。

父 `tmp/downside_max10_20261105_late_v4` 已完成417/646日、累计21次新选择、1585.3732661000104秒。通用父链复核四代sidecar归属2+3+3+13，各自保留原pins。重放时完整args匹配；417行最新前缀通过前禁止新搜索。累计上限仍31次/10800秒、每月600秒。

v4已有META、CEG、AZN、CTSH配对材料继续保留；仅追加已独审LRCX股息artifact。生成freeze前先在文档副本注入所有配对，再对父2025-08-29真实exposure调用既有 `admit_reviewed_dividends`，未清除LRCX 9/24阻塞不得标READY。无新选股或经济运行。

准备入口：`python -m scripts.research.prepare_downside_max10_resume_v5_freeze_20261105 --artifact <LRCX配对路径>=<已确认SHA256>`。

根审后经济入口：`python -m scripts.research.run_downside_account_candidate_20261105_v5 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v4 --output tmp/downside_max10_20261105_late_v5`。本轮不自动启动。

测试覆盖真实四代归属/预算/417行边界及缺LRCX时原gate仍拒绝；不代表完整经济策略通过。
