# ROA月度换仓衔接

月末自动准备与生产正式采用是两步。当前经济规则不变；不得用前月名单代替未验证的新月名单。

## 已有入口

1. `scripts.run_local_roa_monthly_preparation`：核对固定绑定的活动版本与来源，月末收盘后采集、训练、准备月份包及注册方案；不自动采用。
2. `scripts.research.prepare_roa_monthly_publication`：只允许月份注册追加，核对当前及候选V34完整来源链。
3. `scripts.research.adopt_roa_monthly_registration`：显式执行后原子切换活动配置指针；指针已换不等于服务已加载。
4. `scripts.inspect_roa_monthly_preparation`：只读检查descriptor、活动配置和准备状态。输出锁待核对时不能推断任务仍活跃，更不能直接删除锁重跑。

从仓库PowerShell运行状态检查，参数使用当前任务Action中的实际descriptor引用：

```powershell
D:/python/python.exe -B -m scripts.inspect_roa_monthly_preparation --descriptor-path <当前descriptor路径> --descriptor-sha256 <当前descriptor的SHA256>
```

## 尚未完成的自动衔接

- 月包采用后，须检查实际加载的配置与目标月份、受控重启完成、账户及完整账本前后不变。现有正式采用入口不能独立证明这些。
- 成功采用后须准备下一月份计划并重新绑定该任务。`scripts.build_monthly_successor_plan.build_next_plan`已有严格下一月边界生成逻辑，可复用；缺少下一月可信日历时应明确等待补齐，不能猜测日期。
- 失败尝试及其原始输入要保留；恢复需核对失败指纹和当前版本后建立新尝试。当前不得清除失败文件或无界自动重试。

真实首个新月执行窗口、用户成交、部分成交或撤单按真实事件验收。隔离测试及只读状态检查均不替代这些证据。

## 收尾工具与已部署的运行版本接口

`finish_roa_monthly_adoption`及Windows CLI `finish_roa_monthly_windows`保留重启意图、前后账本和运行态证据，未知重启结果只核对，不重复启动。Windows适配器绑定旧/新进程的PID、创建时间和完整命令行，并核对HTTP读取前后的监听进程一致。

它依赖启动时固定的`/api/strategy-roa/runtime-binding`接口。2026-11-07已正式挂载并通过实际HTTP核验，启动配置SHA及月份注册表与发布包一致。收尾工具尚未用于真实未来月包采用；接口上线不等于自动月度换仓已验收。隔离测试不替代真实未来月份验收。

## 下一轮草案与失败恢复入口

- `scripts.research.draft_roa_next_month`读取正式采用、运行验收、活动版本、采集封印及可信日历引用，复用既有下一月生成器写出request/launcher草案，不安装任务。隔离测试覆盖成功、已有目录、缺日历、活动版本变化、未正式采用。另已通过真实下一月生成器及capture-plan验证器的衔接测试：合成的11月完成证据生成12月计划，决策日11月30日、训练窗口253日，未到收盘仍不可采集；该项仅launcher来源发现使用替身。未声称真实2027月包或任务安装可用。
- `scripts.prepare_roa_monthly_retry`默认只读预览。显式`--prepare`也只生成新目录内的capture plan/request/launcher，不执行采集、不改任务。必须提供当前descriptor、其blocked.json的精确SHA及复核原因，保留旧失败及半成品；存在锁、旧active改变、完成记录或路径重叠时拒绝。真实失败原因仍须先处理，不能靠新尝试绕过数据或来源校验。

以上新增工具尚未接入常驻自动采用流程；当前线上任务仍仅准备月包。所有实际注册、启动和首个新月执行验收均须保留独立证据。

2026-11-07补充：runtime-binding候选已执行真实候选mount、完整V34构建及来源校验，约232秒通过；配置引用、active SHA和月份注册表与候选加载值逐项相符。当前注册表为空，不能由此声称未来月份已准备好。该验证未启动服务lifespan、未替换生产源码。候选V34静态来源集合显式新增runtime-binding模块，回滚必须同时还原mount、V34及active。正式发布包使用本地`research_contracts/roa_runtime_binding_20261107_v2`；v1已被路由冲突修复取代。

2026-11-07 01:05正式部署：runtime-binding v2运行验证通过，29层配置引用核对通过；完整账户、账本、绩效基准及sidecar部署前后不变。页面确认STX 7股、ODFL未成交22股，因STX成交后缺最新购买力而显示WAIT_CASH_CONFIRMATION，未宣称可执行建议通过。月度准备任务Action重绑runtime_v6（683来源），其他12项金融任务不变；当前expected_month=2026-12，状态CONFIGURATION_VALID_NO_COMPLETION。只读页面取证屏蔽非GET及图表请求，不代替现金保存、图表或真实未来月份验收。

## 后继准备任务安装

`scripts/rebind_local_roa_monthly_preparation.ps1`将已复核的新launcher绑定到现有同名月度准备任务。默认只读预检；`-Apply`要求当前任务XML的SHA256及新的私有tmp证据目录。参数为`-ConfigPath`、`-ConfigSha256`、`-ExpectedTaskSha256`，应用时另加`-EvidenceDirectory`。只更新Action，不启动任务，保持Triggers、Principal和Settings；保存前后XML及成功回执。任务正在运行或版本变化时拒绝，部分失败先查看已保存证据，不盲目重试。

2026-11-07验证：当前683来源launcher真实只读预检通过，真实任务XML未变；`tests/rebind_roa_monthly_task_mock.ps1`使用替代Windows调度接口验证Action更新、非Action字段保留、旧任务SHA拒绝覆盖。该测试不证明真实未来后继任务已安装；本轮未修改线上任务或服务。

## 准备到运行确认的统一入口

`scripts.research.advance_roa_monthly_release`复用正式adopt和Windows finish入口，默认只读。参数：`--request`、`--request-sha256`、`--output-directory tmp/<新尝试>`；明确执行才加`--execute`。请求字段严格为active、registration、publication（均为path/sha256）、month、epoch、expected_process（pid/creation_date/command_line）。publication必须绑定同一registration和旧active；正式采用仍重新跑完整V34 gate，不复用预检来跳过。

请求与采用意图保存在私有目录，复跑必须同一请求。已切换且有正式adoption回执时不重复采用；有意图但无回执则要求核对，不能凭超时重跑。已记录重启意图但服务未验证时返回WAIT_RUNTIME_RECONCILIATION_NO_REPEAT_RESTART。成功状态为MONTH_ADOPTED_RUNTIME_VERIFIED_NEXT_TASK_PENDING，明确后继计划及任务重绑尚未完成，不标记整条换月结束。

6项编排隔离测试通过（采用/finish适配器使用替身）：只读无输出、重复运行、切换后丢失确认、未知切换拒绝重复、启动等待不重复重启、后续active不覆盖。尚未对真实未来月包执行此统一入口，尚未纳入常驻调度；账户、服务和任务未改动。

## 可恢复的完整后继衔接

统一advance请求可增加`successor`：包含`inputs`（manifest、completion、capture_receipt、training_calendar、session_calendar、calendar_path、calendar_source_hashes）、python_path及expected_task_sha256。运行确认后自动使用实际adoption/validated/runtime-success与新active生成引用，再调用真实下一月生成器和Action-only重绑入口。缺日历或存在半成品时停在可核对状态，不伪造日期、不覆盖旧输出。

`finish_roa_next_month`只在advance持有尝试锁时调用。已保存draft复用前核对来源及launcher预检；任务更新成功回执必须与当前任务XML SHA一致。存在更新证据目录但无成功回执时拒绝自动重复更新；成功后出现新的任务配置同样拒绝覆盖。完整状态MONTH_RUNTIME_AND_NEXT_TASK_VERIFIED只说明运行配置与下一月任务绑定，不代表页面、真实成交或未来执行窗口已验收。

本轮12项隔离编排测试通过：advance 7项、后继任务5项，其中覆盖更新后丢失确认、未知更新、后续任务变化及实际采用回执引用传递。外部采用/进程/调度适配器使用替身；此前真实生成器和当前任务只读预检独立通过。尚未将此统一入口接入无人值守采用调度，未对真实未来月份执行；当前真实账户/服务/任务不变。

2026-11-07组合验收补充：`test_roa_monthly_integrated_adoption.py`两项测试使用真实注册、发布、active原子采用、finish协调器及SQLite账本；重复进入只调用一次模拟重启，实际回执与active SHA一致，回滚字节完整。模拟并发现金更新时保留新账本并拒绝success，重试不重复重启。月度输入为合成fixture，V34完整服务构建与进程适配器使用替身；不包含真实未来月份或后继任务安装。不得将它扩大称为全生产端到端通过。

## 从实际准备任务生成采用请求

`scripts.research.build_roa_monthly_adoption_request --descriptor-path ... --descriptor-sha256 ...`读取固定准备任务、完成记录、正式publication及采集封印，并核对当前8010加载的active/config/epoch与读取前后的进程身份。只有同一月包完成后返回ADOPTION_REQUEST_PREPARED_NOT_EXECUTED；可用`--output tmp/.../request.json`排他写出统一advance请求。不会自动采用、重启或安装任务。未完成返回WAIT_PREPARED_MONTH；异常配置、失败或锁待核对返回PREPARATION_REVIEW_REQUIRED，不能当作正常等待。

请求包含后继计划输入；日历是否覆盖下一月仍由正式draft验证器核实，返回中明确successor_calendar_fully_validated=false。若未来日历不足，应先补可信日历，不可在生产猜测日期。

2026-11-07当前runtime_v6真实只读调用返回12月CONFIGURATION_VALID_NO_COMPLETION，未创建请求。6项隔离输入测试覆盖正常生成、尚未完成、错误状态区分、服务旧版本、月份冲突及采集内容改变。尚未接入无人值守采用触发，不能宣称已自动执行真实新月。
