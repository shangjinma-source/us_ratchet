# AI复核延迟：既有记录与当前源码只读定位

本轮读取 `tmp/cash_noop_ai_ui_20261104_2330/responses.json`、正式service/composition/router及既有性能报告。没有请求模型、保存现金、启动服务、重新回测或修改生产。以下为该次记录，不保证当前每次耗时相同。

## 已能定位的部分

该次点击至显示306.941秒；job started到结果ready约212.748秒，worker计时212.559秒；本次模型lookup52.912秒（模型receipt推理约52.739秒）。所以换更快模型不能单独解决完整等待。

| 阶段 | 秒 | 当前可证明的含义 |
|---|---:|---|
| parallel_capture_preview | 66.193 | 外层总计，不能再与子阶段相加 |
| initial_bound_context | 0.982 | 已进入snapshot作用域后的上下文 |
| initial_preview | 25.682 | 同作用域内建议计算 |
| news_capture | 7.225 | 与上述策略读取并行 |
| 初始外层未分解差额 | 39.529 | 66.193−0.982−25.682；包括作用域进入/排队等，不能全称锁等待 |
| post_analysis_inputs | 45.578 | 新作用域读取及模型后建议 |
| 其中post_analysis_preview | 27.055 | 不与父阶段重复相加 |
| 模型后其他差额 | 18.522 | 作用域进入、bound_context、调度等尚未拆开 |
| final_validation | 18.666 | background guard、独立bound_context、新闻/时限校验等 |

`data/news_investment_service_v1.py` 的 `strategy_inputs()` 在 `measured(initial_bound_context/initial_preview)` **之前**进入 `input_operation`。`data/strategy_account_rolling_router.py:snapshot_operation` 先取得 `self.lock`，再同步调用 `_snapshot_provider()`，之后才yield。所以39.529秒可能包括RLock等待与昂贵发布快照获取；现记录无法分摊。

源码存在合理的独立重验：并行输入返回后再 `self.bound_context(binding)`；模型后 `background_guard(answer)`；模型后新的scope；最终validation；COMPLETE结果返回时再查绑定。按不重复计算的阶段相加，worker仍有约29.114秒落在未单独计时的context/guard/其他工作。不能将此差额归给模型或重复加总并行子阶段。

点击→job started约83.98秒发生在worker计时之前。`NewsInvestmentService.start()` 会先调用bound_context再设置started_at；HTTP路由还有validate，前端有现金后目标/建议请求。故其中**至少存在未被job计时覆盖的启动上下文**，但现responses没有完整每个请求起止，不能把83.98秒全称线程池排队。

COMPLETE→显示约10.21秒也不能全称前端轮询：`status()` 对COMPLETE仍做bound_context及background_guard，可能产生一次新的发布读取；RUNNING已走轻量路径，不应再次“优化”成早已实现的行为。

## 已部署优化不得重做

`docs/news_context_performance_20261104.md`已记录单次lstat路径检查和模型前context/preview共享snapshot已部署；`docs/news_post_analysis_scope_20261104.md`记录模型后读取对共享新的scope已部署。当前正式源码确实包含这些实现。context依旧validate两层不等于应该直接删校验，完整provider历史约10秒也不是全部模型工作。

## 只建议一个下一步

**针对同一snapshot入口做有界分段测量，随后只合并被证明确属同一操作的重复获取。** 最小诊断应区分 lock_wait、snapshot_provider、作用域内工作，并记录调用阶段/线程/嵌套深度；补start前bound_context、parallel后bound_context、post context、background guard、COMPLETE status验证计时。不要先缓存跨模型快照、延长报价寿命或删除最后重验。

可验证方案：先用隔离真实router和计数provider证明嵌套调用只读一次、并发锁等待单独归类、异常仍释放，再在下一次本来就授权的复核中收一次完整链时间。不是为了测量重新调用模型。若provider耗时占主导，优先在该操作内消除确证的重复source验证；若锁等待主导，再针对实际锁持有者缩短不必要工作。缺这一步证据，当前不承诺节省39.5秒，也不提出多项微调或单独重启。

本轮只有可核验的瓶颈边界与一个测量方向，尚无新的提速部署成果。

## 一次V32隔离实测（随后完成）

独立计时工具与3项真实RollingMonthlyRuntimeRouter夹具通过：嵌套provider只调用一次、并发等待与provider分别记录、异常释放和原lock/provider恢复。代理保留acquire参数/结果，失败acquire不计held；聚合只用最外层，避免重复计算嵌套持有时间。

初次沿旧脚本V29构建器约1秒即被V29_CONFIGURATION拒绝，未执行context；失败日志保留。核实实际活动文件虽然名为config-29.json，内容schema为V32后，按根授权修正为正式V32构建器，构建前核配置字节hash与schema，只运行一次新诊断。

| V32独立进程一次测量 | 秒 |
|---|---:|
| 服务构建 | 191.9754 |
| 一次service.context | 9.25085 |
| 唯一snapshot_provider调用 | 8.27208 |
| 最外层RLock等待 | 0.0000011 |

provider约占context的89.4%。此进程没有生产竞争者，**不能用微秒锁等待证明实际服务器不存在锁竞争，也不能用8.27秒解释旧39.53秒全部差额**。只能确认在当前活动配置下，独立完整发布快照获取仍有可观成本；初始共享scope已生效，不能再通过同一步去重节约一遍。

实际账户/目标完整内容前后相等，活动配置字节前后相等，线程集合前后相等；没有执行startup hooks、新闻worker或模型。原进程自然退出0，未重启或重复构建。证据：`tmp/news_context_boundary_profile_v32_20261105/report.json`及同名前缀stdout/stderr日志；旧失败日志仍在 `tmp/news_context_boundary_profile_20261105.stderr.log`。计时脚本为 `scripts/research/profile_news_context_boundaries_20261105.py`，代理为 `snapshot_timing_probe_20261105.py`。

没有新的生产提速结论；下一次授权的正常端到端操作仍需区分真实锁持有者与快照provider耗时，不能据此删掉独立绑定校验或增加跨请求缓存。

## 后续静态核查边界

V32经V28安装的实际provider仍走upgrade_handoff和replayed activation。首尾base_provider是发布变化检测，不能删除；BoundedSourceGate单调用路径去重、重放缓存及单次lstat已存在，不重复实施。剩余疑点为ReadDependencies.checked_read后MonthlyFileConfiguration._read再次检查路径元数据，尚无累计耗时占比，不能据此宣称找到主要瓶颈。下一步仅允许一次context的cProfile取证，构建不计入profile，无模型/启动hook/账户写入；若没有明显且安全的收益，结束该微优化方向。

## 最后一次函数级取证与收束

单次V32进程构建187.396秒，cProfile只覆盖context：13.0345秒，其中provider11.5820秒。分析器有运行开销，不与无profile的9.25秒直接作性能优劣比较。两次历史发布_validate_saved累计9.948秒，重放缓存4次verify累计3.606秒，282126次nt.stat自身3.588秒，11次V27 gate累计2.133秒，2次training compile累计1.480秒。这些调用存在父子包含，不能相加当总耗时。

账户、目标、活动配置和线程集合未变，context结果hash与上次相同，startup/model均0，进程退出0。证据tmp/news_context_cprofile_v32_20261105/{report.json,context.prof,cumulative.txt,self_time.txt}。未找到收益明确且可安全删除的主要工作，停止该微优化分支；不再启动profile、不删重验、不改生产。端到端刷新慢尚未解决，独立进程无法解释线上锁竞争，后续仅随真实端到端使用采集，不为了性能测量单独调用模型。
