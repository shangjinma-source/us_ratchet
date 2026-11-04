# AI 复核上下文性能定位（2026-11-04）

在独立进程按当前 scheduled_ai_runtime 配置构建实际服务，不执行 startup hooks、不启动第二个新闻 worker、不调用模型。构建耗时 201.725 秒。一次真实 service.context() 的 cProfile 耗时 16.758 秒；完整账户、月目标前后相同。

主要开销：snapshot provider 14.900 秒，占约 89%；两次历史发布验证 12.382 秒。调用链保留前后发布一致性检查，不能直接删除第二次验证。文件 stat 共 481622 次，累计 6.724 秒；缓存命中仍需完整校验源字节，这是正确性要求。

完整候选文件：docs/candidates/strategy_release_replay_cache_single_stat.py。仅把每个路径组件的 is_symlink/exists/lstat 三次状态查询改为一次 lstat，同时拒绝符号链接及 Windows reparse 属性；缺失源仍交原读入器拒绝。不缓存文件状态、不跳过哈希、不变更缓存键与结果。

验证：原 8 项回归全通过无跳过，覆盖同大小同时间戳篡改、源缺失、计算期间变更、符号链接、缓存隔离、容量、并发；另验证 Windows reparse 属性拒绝。交替顺序 5 轮、每轮 500 次实际源码读取，中位数 0.233 秒降至 0.163 秒（约 29.8%）。仅局部微基准，不能外推为整条复核提速。

本地证据：tmp/news_context_profile_20261104/{report.json,context.prof,context_cumulative.txt,candidate_benchmark.json}。诊断脚本 tmp/profile_news_context_20261104.py 与 tmp/test_replay_single_stat_20261104.py。生产文件未修改，候选未上线。

下一步：在一个独立服务实例中交替对照原与候选完整 context 读取，检查结果完全一致与账户未变；若实际节约有意义，再合并正式源码绑定配置部署。不要为了小幅微基准收益重复重启生产。后续还需判断多次完整发布读取能否在不跨模型等待、不延长报价期限的操作边界内合并。

## 完整上下文交替对照

同一独立实例构建耗时 203.245 秒；未运行 cProfile 的计时按原版、候选、候选、原版顺序进行。原版为 11.720/11.524 秒，候选为 10.116/10.188 秒。中位数差 1.470 秒，约 12.6%。四次上下文返回值完全一致，真实账户及目标前后快照一致；未运行 startup hooks、模型、新闻采集或交易写入。证据 tmp/news_context_profile_20261104/full_context_comparison.json；运行脚本 tmp/compare_news_context_20261104.py。

结论：候选确实改善完整上下文读取，但不足以解决约 278 秒的复核任务耗时。本轮不单独重启部署，保留在后续有意义的性能补丁中合并。继续查复核各阶段重复构建与校验，保留模型等待前后的账户变化检测，不把候选微基准 30% 冒称为端到端提速。上一段“下一步完整对照”已完成；当前优先级转为整条复核流程。

## 初始上下文与建议共享操作快照候选

发现初始 bound_context 与紧接着的 initial_preview 各启动一次历史发布快照校验。新增完整 service/composition 候选：docs/candidates/news_investment_service_scoped_inputs.py 和 news_investment_composition_scoped_inputs.py。组合层明确注入 monthly_view.snapshot_operation；策略输入在线程池同一线程内读取账户/目标并计算建议，复用当前操作内发布快照。新闻采集仍并行。该 scope 在模型调用之前退出，不跨模型等待保留旧发布状态或账户锁。

模型前后及最终 bound_context、第二次 fresh preview、新闻 generation、报价期限、财报日程绑定全部保留；未注入 scope 的原调用路径保持兼容。没有放宽六分钟任务期限或行情新鲜度。

16 项隔离测试通过：原服务 13 项回归，加同线程 scope 共享/模型前释放、异常释放及真实 RollingMonthlyRuntimeRouter.snapshot_operation 的 provider 调用计数。初始两步共一次 provider 读取；保留后续独立检查。测试文件 tests/test_news_scoped_input_candidate.py，不调用外部模型或采集，不写真实账户。按已测单次快照成本预计能减少约十秒以上，但尚未做真实端到端测量，不能声称已达到。

下一步优先将两份候选与财报日程接线集成回归，核验生产配置后整体部署；可同时合并已验证单次 lstat 优化，减少重复重启。部署前要保留源码/活动配置回退材料；此处三份性能候选目前均未上线。不要把单线程作用域单测视为盘中完整验收。

## 2026-11-04 AI 初始读取共享快照与路径检查优化已部署

正式 service/composition 接入 input_operation：初始账户/目标与初始建议计算在同一策略线程共享一次操作内发布快照，模型运行前释放；模型后的账户、目标、报价和新闻重验均保留。正式 replay cache 路径检查每层改为一次 lstat，仍逐次完整读取并核验源字节，不以文件大小/时间戳代替 hash。V27 交易策略不变。

独立 scoped_ai_runtime_20261104_v27_r1/v28_r1/v29_r1 配置部署到 8010，PID15152。GET账户200/0.221秒、月目标200/10.111秒、日历脚本200/0.323秒；三层配置与源文件hash通过，完整账户与目标快照一致。新闻worker enabled/worker_alive为true，无worker错误；SNDK发布时间冲突仍未解决。

验证：共享快照及日历19项集成测试；生产源码服务13项、缓存8项、日历3项回归通过。已测路径优化完整context从约11.62秒降至10.15秒；新增共享快照减少初始一轮provider读取的机制已测试，但没有当前盘中端到端实测，不声称278秒任务已解决。

本地回退/验收目录tmp/scoped_ai_deployment_20261104。回退只恢复previous__三份源码和previous_active.json，不恢复账户数据库。当前仍待：盘中现金按钮到AI结果的完整耗时/有效期验收、真实成交承接、新闻策略经济效果；不自动制造成交。


## 已失效结果轮询的提前拒绝候选

生产 GET 已有 COMPLETE 历史任务、未创建新任务或调用模型，返回 STALE 仍耗时 11.366 秒（tmp/news_context_profile_20261104/status_baseline.json）。status 在读取账户/目标之后才判断结果期限，导致明显已过期的结果也重复执行完整历史校验。

候选 docs/candidates/news_investment_service_status_preflight.py 对 COMPLETE 先检查复核期限、READY风险方案期限、新闻generation；任一失效立即返回原有 STALE/REFRESH_ACCOUNT_AND_REVIEW，不提供proposal。原完整context/background及其后的时效、风险期限、新闻generation检查保持，防止校验途中失效。RUNNING和失败任务语义不变。

5项测试通过（tests/test_news_status_preflight_candidate.py）：已过期、新闻已变跳过context；有效结果仍检查账户；context耗时造成过期仍拒收；context期间新闻更新仍拒收。候选未部署，不能将该早退宣称为有效复核或AI计算提速。后续合入正式源码配置并测量同一历史任务GET，生产工作台目前继续使用6b46774。

## 2026-11-04 失效 AI 结果提前拒绝已部署

正式 service.status 对 COMPLETE 结果先检查复核期限、READY 风险期限与新闻 generation；明确失效立即返回 STALE，不返回 proposal。完整账户/目标/背景校验后仍重复检查时效与新闻变化，未削弱有效结果校验。生产 13 项回归与候选 5 项边界测试通过。

独立 status_ai_runtime_20261104_v27_r1/v28_r1/v29_r1 配置已部署，8010 PID7740。账户200/0.164秒、月目标200/10.167秒、静态脚本200/0.300秒；配置及源码hash通过，账户与目标完整快照未变，新闻worker存活且无worker错误。SNDK发布时间冲突仍未解决。

生产已有过期 COMPLETE 任务 GET 返回 STALE 且无 proposal，耗时0.278秒；前次同类历史任务GET为11.366秒。不是AI推理、盘中有效建议或端到端现金操作的性能验证。本次没有启动模型或写现金、成交。证据与源码/活动配置回退材料位于tmp/status_ai_deployment_20261104；禁止恢复账户数据库快照。

性能微调本轮收束，后续优先整体验收现金→当前建议→AI有效结果及真实成交承接，不继续无界新增微型优化。当前仍缺盘中完整链的最新部署验收和用户真实成交事件，Goal未完成。

