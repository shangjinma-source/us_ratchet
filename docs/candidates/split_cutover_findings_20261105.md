# 生产切换入口实读结论

`start_service.ps1`启动8010，但已有健康服务时直接返回already_running，不证明加载配置版本。`api/strategy_server_mount_v8.py`仅启动构造前后检查active指针；修改指针本身不会撤销旧进程的账户写权限。`publish_monthly_market_configuration.py`输出未激活资料，月度release SQLite CAS也不是全服务切换。

三时点bundle与bound_split_sources已能准备并核对旧账户/目标/风险；持锁内只做本地工作，不能联网或等待模型。它们不会排空旧请求、停止进程或阻止并行启动者，不能据此宣称原子上线。当前源锁读取旧StrategyAccountStore，仅适用于第一次旧账本迁移。

正式部署仍需：准备并验证候选配置→排空写请求和确认实际写入者→旧进程退出→重验最终三库及准备包→持锁内发布配置→正式入口启动一次→验证新PID、加载配置和账户/current/news绑定。原金融任务不能默默停用，必须处理其原写路径。尚未执行此流程。

仅升级代码的回退必须继续使用最新账户库；禁止恢复旧数据库快照。真实拆股新库若已有后续现金或成交，不允许回退到旧库丢弃后缀，应保留新库修复兼容代码或单独验证后缀迁移。

## 11月5日实际任务与线程复核

- Windows任务 `UsRatchet-DailySource-Evidence` 当前Ready、带Execute，配置为 `research_contracts/daily_rss_recovery_20261022_v5/configuration.json`。该配置固定读取 `data/strategy_account/real_strategy.sqlite3` 与 `data/strategy_account/monthly_targets.sqlite3`。
- 其实际入口 `run_local_dynamic_daily_sources_v5.ps1` → `run_daily_dynamic_source_v5.py` 使用旧 `StrategyAccountStore`。代码仅read账户/目标，不调用append；资料任务本身不能据此称为账户写入者。但切换新账本路径/格式时必须同步读端，不能只切8010而让原任务继续读取旧状态。
- `UsRatchet-CurrentAdvice-Followup` 当前Ready，入口为 `run_local_current_followups_v1.ps1`；其输出与其他任务仍需分别核对，不能把一次任务清单当作全部后台写入者证明。
- 实际 `news_event_pipeline_v1.stop_worker` 只设置stop_event并join两秒，未核实线程已退出。HTTP测试中mock的启动/停止次数不能证明排空，正在以真实可控线程验证超时拒绝切换与最终退出。
- 当前Windows任务清单中 `us_ratchet_golden_pit_snapshot` 为Ready；旧操作笔记的disabled描述不能替代当前状态。本轮不改变该任务或任何其他任务。

以上均为只读核验，未停止线程、服务或定时任务，未创建真实成交。OpenClaw/Codex调度与其他进程尚未据此宣称全面排空。

已新增未挂载的 `runtime_service_quiesce_20261105.ServiceQuiescer`：在服务所有者独占生命周期的前提下，先关闭HTTP入口、按同一总时限等待实际请求，再对注册新闻线程发停止信号并核验真实退出及线程对象未替换。HTTP/线程超时均保持入口关闭；成功也仅证明该入口及该线程排空，`may_switch`始终false，不擅自切换或恢复。真实请求取消后仍等待底层任务、线程join返回仍存活、最后实际退出的综合测试通过；根线程独立复跑1项0.069秒。尚未接入生产生命周期。

## 独立AI复核线程尚未纳入

实读 `NewsInvestmentService.start`：每次复核另起名为 `investment-review` 的daemon Thread；实例没有保存线程句柄，全局 `_workers` 仅记录job ID。HTTP请求返回202后，该线程继续运行；EventNewsPipeline.worker退出也不代表它结束。`run`还可能进行重新报价和原生风险资料写入，不能把它当作没有状态影响的纯模型调用。

因此当前ServiceQuiescer成功仅覆盖其明示的一条新闻发现线程，不能允许切换。后续须在新服务装配时登记复核线程并串行化“关闭接入/创建线程”，关闭后不得再创建job；同一总超时内等待实际线程退出（不强杀模型线程），再做最终存储复核。超时保持旧进程和账户，不发布新配置。需要覆盖HTTP已返回但复核仍运行、关闭与启动竞争、最终退出这三种情况。此发现未改生产源文件或任何任务。
