# AI复核重复校验候选优化

生产证据：本地 job_stored.json记录约349秒，模型缓存约0.192秒，post_analysis_inputs约118秒，final_validation约49秒。不能把总耗时归因模型。生产未修改，未新增模型请求。

## 单一机制

NewsInvestmentService.bound_context先self.validate，再调用composition.context；后者在monthly.snapshot_operation内又调用完整validate。每次绑定检查至少重复一次相同配置/源代码字节校验。RollingMonthlyRuntimeRouter.snapshot_operation本身还串行获取lock、调用snapshot_provider，现有计时未拆开锁等待与provider，因此不能断言118秒全部可消除。

候选仅增加显式context_validates_sources参数，默认为False；只有已审阅的composition传True。完整校验仍在持锁context内运行，每次bound_context重新执行。初始、模型后、最终context与revision/proposal重读及报价/任务期限检查均保留。不延长有效期、不跨模型缓存账户、不新增并行锁范围。

文件：news_investment_service_context_validation_20261106.py、news_investment_composition_context_validation_20261106.py。组合候选显式导入候选service，未被活动配置引用。

测试test_news_context_validation_20261106.py证明：默认保留两次校验；显式可信context每次一遍；后续源更改失败；revision变化失败。模拟计数只证明消除重复调用，不是实测线上耗时。尚需独立审查sourcepins更新、隔离真实composition profiling及最后实际UI任务验证，才能声称及时性改善。此候选不会解决全部锁等待/发布provider开销。


## 真实组合验证补充

实际执行compose的隔离测试已补齐（仅技能加载、月度对象依赖替身；真实composition/service/event pipeline/router构造执行，不启动worker）。确认bound_context完整validate在snapshot_operation内；后续source改变和revision改变仍拒绝；无内置校验context默认外部validate。共3项测试通过。

可部署composition候选另存 `news_investment_composition_context_validation_deploy_20261106.py`，导入正式 `data.news_investment_service_v1`，不得部署带docs.candidates导入的测试组合。

7个服务相关回归文件共58项：候选51通过、7失败；独立进程生产基线同58项也是51通过、同7项失败（STALE预期而实际FAILED）。失败分布：stage_timing 1、risk_plan_service 1、reference_service 5。无新增回归失败，但不能称全绿，状态语义现存问题需另外处理。未为通过测试更改预期。


## 七项旧断言失败的具体原因

引入点为提交 `7dc15d35307d8cfce7c58ce99b33eb80b7804f4c`（2026-11-04）：status()对已保存FAILED任务直接返回白名单，避免失败任务再次等待账户/目标锁。并非本次去重变化，也非deadline变化。

调用链：run()中的initial bound_context、模型后reference检查或risk callback抛STALE_ACCOUNT_OR_TARGET/REFERENCE_REVIEW_CHANGED → run except保存FAILED → status提前返回FAILED。旧版本status继续调用bound_context，再抛一次并返回STALE；7项测试仍要求旧显示状态。模型失败、超时等继续FAILED；原COMPLETE任务后来失效仍在status完整校验后返回STALE。

终态返回白名单不含proposal/binding；web/news_investment_review.js accept仅接纳COMPLETE且有效的proposal，FAILED与STALE均清空proposal并释放busy，receiveFlight也只轮询RUNNING/QUEUED/STARTED。用户可重试；start仍执行最新绑定检查及一分钟冷却、每日预算。未发现因这7项状态变化错误复用意见。

建议保留失败终态快速返回，不为旧测试恢复昂贵锁重读。若更新回归契约，应断言FAILED、具体原因、没有proposal/binding以及后续可重试；本任务未修改原测试或语义。当前去重候选与生产基线失败完全相同，无新增失败。


## 终态契约回归收尾

经主线程明确授权，7项旧断言已更新为实际既定终态：FAILED、明确STALE_ACCOUNT_OR_TARGET或REFERENCE_REVIEW_CHANGED、无proposal及binding。未恢复昂贵重读，未修改运行状态语义。更新后独立进程生产基线58/58通过，候选58/58通过，日志在本地tmp/news_context_dedup_regression_20261106。

新增前端tests/news_investment_terminal_retry_20261106.cjs验证真实UI控制器：FAILED和STALE均清空已显示旧意见，随后显式start可发新请求并显示新结果。该测试通过；不包含网络或真实账户写入。

## 部署进度

上述候选已由主线程部署，活动配置 `research_contracts/news_context_dedup_20261106/config-25.json`，SHA256 `5ca8698439a74f28bfe56a6d61fb818f7d31469a0c12f3655dd0cecd9e09dfb0`。部署源码与准备材料一致，账户、月目标完整快照未变。服务启动后首页 HTTP 200；单次相同现金按钮链路正在测量，尚未证明实际延迟降低。生产 composition 使用正式 data 模块路径，不从候选目录加载。

## 单次真实按钮结果

本次单击使用已有已确认余额：点击至测试收尾 240.619 秒，后台任务 COMPLETE，运行 141.653 秒。没有现金保存或成交请求，账户前后完全一致；实际 POST 仅日历刷新与 AI 复核。没有复用该结果宣称真实新余额写入通过。

优化前最近三次完成任务分别为 120.433、185.169、349.203 秒；不同负载和缓存条件，不能只选最慢基准宣称提速。本次 final_validation 9.519 秒，post_analysis_inputs 44.923 秒，parallel_capture_preview 56.630 秒；模型分析缓存读取 0.048 秒。尚不满足快速反馈目标。

点击至收尾与后台任务时长相差约 99 秒，包含按钮刷新、同步 start 校验、轮询和收尾，当前证据不能把它全部归因于某一函数。前端在刷新当前建议完成后才发起 AI；start 在创建后台任务前仍调用 bound_context。下一步需分别计时，不延长报价有效期，也不通过省略账户/目标绑定检查换取速度。私人原始证据保存在本地 tmp/cash_button_live_20261106_r3。
