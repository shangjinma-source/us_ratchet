# 当前 V27 接线核对（只读）

结论：当前 V27 本来就是 saved-frontier CAP50/EXIT20。新三时点单位工程可接当前策略，不需要采用已否决的 downside-max10/cap20。名称相近不代表同一实验。

实读 `config/strategy_server_active.json` 指向 `research_contracts/news_calendar_selection_20261105/config-29.json`，SHA793857ec0088247245ddacd59f1a5254b9c63025f7ddef00d143793d360f4d31；逐层base配置hash核验到config-24（V27）。该层引用 `research_contracts/frontier_runtime_20261025_v27_r1/release.json`：SAVED_FRONTIER_CAP50_EXIT20_V1、monthly_cap=1/2、exit_ratio=4/5、sma20_overlay=false。外层V28–32负责新闻/快照/当前建议读取，不是另一个交易策略。

## 实际接点

`data/strategy_unified_server_preparation_v27.py:124` 建 proposal store/monthly view；132 建 `SavedFrontierLiveReader`；137 建 `SavedFrontierRollingAdmissionV1`。后者 `data/saved_frontier_rolling_admission_v1.py:27` 在原monthly.snapshot_operation内取得 `_for_target(target)` 的真实执行provider，再为单次请求复制并安装：DailyMarketCaptureV3、HaltGzipMarketCaptureV1、strategy_recent_minute_retry_v1、按日Halt PullbackCapStore（继承legacy cap）、GzipActionCapture，最后原DailyComposition。三时点测试使用的basic splitprovider不能直接取代这一层，否则会丢失停牌、真实transport时间和分钟重采保护。

最小实用路径：保持原selector/32连续搜索、frontier proposal、cap50、20%退出、同月禁买回、费用与全部外层API/AI不变；仅在已准备并认证的split generation中替换原ledger/runtime及source-history坐标读取，创建保留上述保护的隔离rolling admission。无split仍走原生产路径。报价、停牌、限价均沿真实原证据闭包；新增transition另绑定原target/proposal，不重签成新单位月目标。

新reader的研究policy字符串不能直接冒充生产授权。工厂还需显式绑定既有CAP50_EXIT20 release、当前target/proposal及候选执行源码闭包；若需对research receipt增加release envelope应留原receipt不变，不能直接改policy_id假装原source gate已经批准新代码。

## 账户及激活边界（由根线程另行处理）

`MonthlyRuntimeRouter`在`data/strategy_account_monthly_router.py:49`及runtime builder硬接ScopedAccountStore；`strategy_profiled_release_activation.py`和`strategy_account_release_activation.py`也用旧store/replay。它们的月度数据release CAS不等于账户/目标/风险拆股成组切换。

现成可复用：`strategy_account_split_migration_v1.prepare_split_account`复制并逐事件重放；`strategy_split_bundle_v1.prepare_split_bundle/verify_split_bundle`组合原同钟准备；`strategy_split_write_barrier_v1.freeze_split_sources`按固定顺序锁account/target/risk；`strategy_split_live_binding_v1.bound_split_sources`核真实旧revision/完整target/风险及manifest。三时点需新坐标准备/验证接入，不能误称原bundle已支持。以上都是准备/一致性屏障，尚无生产atomic activation。旧库不可在这些候选完成前原地升级，也不可为回滚恢复旧账本覆盖用户后续成交。

下一实施分工：本agent仅负责`split_production_admission_20261105.py`及专用测试，保留生产daily protections；根负责账户/runtime builder/activation、配置源码闭包、发布与实际来源准入。无真实账户写入、无服务重启、无模型调用。

## 已完成的隔离 admission 接线

`split_production_admission_20261105.py` 现将三时点 reader/provider 接回原 target-bound admission 请求；私有绑定 identity validator 的 split replay，原身份 manifest/hash/持仓及未结单覆盖校验不删。V3 原始报价 transport proof、gzip halt/RSS、原 retry eligibility/实际 2 秒等待和仅一次重采、按日 halt cap store 均保留。limit 额外绑定 timing hash、新单位与 Q/完整会话边界。

`tests/test_split_production_admission_20261105.py` 唯一测试包含正现金、零现金、刚结束分钟全部空值三条子路径。运行 session78541：1 综合测试 PASS，30.955秒。前两条正常卖出 split 后 A 的16股；第三条真实触发 RecentClosedMinuteUnavailable、实际等待2秒、重采仍坏后只卖不买。账户及 prepared SQLite 内容不变。临时实际 sqlite/risk/archive/source normalizer、真实市场/action/limits/差额实现均执行；RSS和halt是合成正文的真实gzip wire。网络完全禁止。

边界：monthly router/view及代码验证回调仍是临时夹具，身份材料与价格时序为受控合成数据；不是生产factory/news/activation全链验收。测试使用明确研究policy，尚未建立生产release/source envelope，不能据此直接替换线上工厂。已验证创建/使用原legacy-backed cap store，但未新增历史非空legacy链迁移经济测试。来源认证、真实broker证据及原子上线由根线程后续统一验证。

根独立复验session60823自然退出0，114.025秒通过5项：discover额外收集了导入的4项日常fixture测试，加本模块1项综合测试。之后仅把fixture导入改为模块引用以避免重复收集，loader核实现在只发现1项；生产候选源码未变，没有为此再次重复长测。三时点准备包及原源锁定随后已由根实现，仍非生产原子切换。
