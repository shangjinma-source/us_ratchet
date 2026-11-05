# 当前 SNDK / MRNA 真实来源准入核验（2026-11-05）

结论：已有真实来源文件可以复用，但当前活动目标不是 native split 目标，现有单位审核不构成 `NativeCaptureReview` 的逐证券口径授权。不能用本次读取自动制造 grant，也不应因此阻塞当前未拆股 V27 正常链。本轮只读既有配置引用与数据库，没有采集、调用模型、生成账户事件或修改运行配置。

## 实际入口与已有证据

- `config/strategy_server_active.json` → `research_contracts/news_calendar_selection_20261105/config-29.json`，配置 SHA256 `793857ec0088247245ddacd59f1a5254b9c63025f7ddef00d143793d360f4d31`；实际 schema V32。沿 base configuration 引用核对的哈希一致。
- 日历：`research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json`，SHA256 `1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af`。
- 身份：`tmp/tri98_runtime_execution_admission_20261016_v10/identity_manifest.json`，SHA256 `30927d384626f02980f024b4525a6ac75895a4ac76f2cbece67e55deded62a23`。两者是活动日资料配置 `research_contracts/daily_rss_recovery_20261022_v5/configuration.json` 的明确引用，已核实际字节，不是本次重新授信。
- 当前月目标位于 `data/strategy_account/monthly_targets.sqlite3`，为 2026-11、2026-11-03 创建；对应已保存 proposal 位于 `data/strategy_account/frontier_v27_proposals.sqlite3`。提案行的 target_id 与当前目标一致。基础 target 数量不能冒充 frontier proposed 数量；本次不重新生成选择。
- 训练 manifest：`tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json`，253 个训练日期为 2025-10-29 至 2026-10-30。它是 `READY_CONDITIONAL_MANIFEST`，自身保留 `complete_corporate_actions_verified=false`、`full_pit_verified=false`、`research_only=true`、`execution_blocked=true`；这些字段不等价于上层活动策略整体停用，也不构成新增单位认证。
- 当前目标的单位基线：`data/strategy_account/evidence/700ee09002d64c6f87fc7e9b1d657ebd/unit_review.json`，SHA256 `4436eeb2db02defd3f5510421292c1a00e2e247f73656def88c761a7d05e04e3`。审核时间 2026-11-03T23:21:55.522508+08:00；状态 `CONDITIONAL_CURRENT_UNITS_REVIEWED`，但 `source_authenticated=false`、`coverage_complete=false`。两只股票历史价格口径均为 `CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN`，当前报价口径为 `CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS`。不能将其改名为 AS_TRADED 即视为认证。

## 两只股票的实际 capture

以下文件均在上述 evidence 目录的 `actions/` 下，文件名本身的 SHA256 已与实际字节核对。

|股票|Receipt|Raw|实际内容范围|
|---|---|---|---|
|MRNA|`8d34b33385035df2c75eda3f2227efda8b669f36ca5b1f0bd9a7e5d1b3412739.json`|`213fcdb5c8bac35437b21feceea50c2098397a92b92043b2a76f496abd330273.raw`|18 个日线时间戳；2026-11-03T15:21:50.116441Z 收到|
|SNDK|`b8a7e3bc5e5e71dedc11d009ec40836685afc96b6c190883b65a3f46537a1114.json`|`d08dcf5cb7efaf1fe14bf421bfc52e2bd7abafd0e8f647f9d35da4d260e16727.raw`|18 个日线时间戳；2026-11-03T15:21:52.758499Z 收到|

两份 receipt 均记录 HTTP200、未截断、请求 dividends/splits，起点 2026-10-09，终点为各自 11/3 盘中采集时刻；原 raw 的 events 为空。只能证明本次响应未返回行动，不能证明未来或所有历史无行动，也不能把采集中未收盘当日 bar 当完整日线。该基线不是截至今天的新鲜行情证明；本轮未遍历全部定时运行归档，不能据此断言系统最新 capture 仍是 11/3。

## NativeCaptureReview 字段映射与精确缺项

|所需字段|可复用项|尚缺 / 不能自动证明|
|---|---|---|
|calendar / identities / source_sha256|上列活动引用与实际哈希|新配置仍须显式绑定相同来源，不自动扩大授权|
|target_id / proposal_id|当前目标与持久化提案|当前 input_binding 无 recorded_split_bindings，source_hashes 无 split-monthly-training-review.json；不满足 native 目标证明|
|baseline closes / unit_id|有真实训练、unit review、capture 字节|需要明确授权的单位标识、逐日正价格及精确重叠映射；现有模糊口径不足以自动宣布 AS_TRADED 或 SPLIT_ADJUSTED_TO_CURRENT_UNIT|
|price_basis / basis_asof / reviewed_at / valid_until|有旧审核与接收时刻|没有在本活动引用链发现满足新 grant schema 的逐 SID 明确价格口径与有效期限授权；不能以 close==adjclose 推断|
|split_schedule / timing_bundles|当前真实账户 SPLIT_CONFIRMED 为 0|尚无真实 native action/training/timing 绑定；未来行动通知不等于实际券商可交易证据，不应现在制造未来到账确认|
|reviewed_dividends / pending_rights|旧 review 的 pending_rights=[]，本次两个 raw 无事件|仅限该已捕获窗口；后续新股息必须有授权精确配对，不能自动从新 raw 加入，也不因此改写现金权益|

最短落地边界：保留当前非拆股路径；新 native 入口保持未激活。将来真实行动进入适用阶段，复用已有原始文件与身份日历，补成明确、限时、限证券的服务端口径授权，绑定真实 prepared/native target 与持久化 proposal 后再接新 reader。缺的不是让用户重复上传现有原文，而是新授权语义以及尚未发生的实际行动证据。本报告不宣称正式准入或部署通过。
