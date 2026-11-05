# Downside max10 v6：INSM无行动审查续接

父late_v5完成502/646日、25份选择、累计1923.490542100044秒；五代记录归属2+3+3+13+4。完整args和各代pins核对，502行前缀未核完不得新搜索。预算仍31次/10800秒，每月600秒。

v6小入口私有加载immutable v3实现，仅替换freeze读取器及artifact dispatcher。ordinary配对仍走原helper；新增 `docs/candidates/downside_absence_artifact_20261105.py` 专门接 `BOUNDED_PROVIDER_ABSENCE_V1`，只加入review.rows/source_hashes。禁止存在dividend_events字段，哪怕空列表也拒绝，不产生任何现金权益。

实际INSM旧receipt没有body_truncated和started_sha256，原 `validate_absence_review` 不能原样通过。新helper不补造字段：严格固定INSM SID、原源路径、2023-12-29→2026-07-30及647会话，复用已冻结WBD legacy inspector 的gzip CRC/长度/hash、明确div/splits请求、URL/符号/返回结构及覆盖校验；receipt/started各自用artifact预期hash认证，并比较ticker和started_at_utc。新schema若原字段齐全仍走旧validator。负面夹具截断、错误symbol、删events请求均拒绝；单capture仍是条件性证据。

INSM `tmp/insm_absence_evidence_20261105/supplement.json` SHA c5b13cea85933011860fe582d7543528bba3fa44544417f583920073f5744aac，单capture明确请求div/splits、完整647会话，条件性provider无行动审查。不是官方穷尽认证，不重新认证已冻结身份/价格。根已接受该既有研究范围。

freeze前实际将review注入副本，对父2025-12-31 gate调用原 `admit_period_absence`；无行动缺口未解除不能READY。普通股息artifact沿前五份保留；不把absence当普通股息传入。

准备入口：`python -m scripts.research.prepare_downside_max10_resume_v6_freeze_20261105 --artifact tmp/insm_absence_evidence_20261105/supplement.json=c5b13cea85933011860fe582d7543528bba3fa44544417f583920073f5744aac`。

根审后经济入口：`python -m scripts.research.run_downside_account_candidate_20261105_v6 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v5 --output tmp/downside_max10_20261105_late_v6`。本轮不自动启动。
