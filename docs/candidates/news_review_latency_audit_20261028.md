# R22 按需新闻复核时效审计

只读现有源码及 `tmp/news_review_release_20261028_r22/actual_ui_job.json`；没有触发账户、报价、新闻或模型请求。此次模型命中缓存，仍需114.963684秒生成结果，不能把历史39.959秒推理时间算成本次模型耗时。

## 已测得与不能拆分的区间

| 阶段 | 现有时点差 | 含义/边界 |
|---|---:|---|
| 请求18:14:43.425538→analysis_started18:15:44.160536 | 60.734998秒 | 包括账户绑定、并行新闻采集与初始daily preview、来源正文组装；没有各子阶段起止，不能将全部归于某个网络源 |
| analysis_started→revalidated18:16:38.389222 | 54.228686秒 | 包括缓存读取/校验、账户重验、第二次完整daily preview；源码显示缓存命中不调用模型，缺缓存结束计时，不能精确拆成预览耗时 |
| revalidated→job.finished18:16:42.312856 | 3.923634秒 | proposal构造、上下文/新闻generation重验和存储路径；不是全部网络耗时 |
| 请求→job.finished | 118.887318秒 | 比proposal.timeliness.total_seconds多末段处理，用户等待应区分两者 |

缓存receipt来自17:20:28→17:21:08的旧推理；当前analysis_completed_at=17:21:08甚至早于当前analysis_started_at。它表示**缓存原分析时间**，不可作为本次结束时间。当前analysis_seconds=39.959同样是原推理时间；应另命名original_model_elapsed_seconds，并增加本次cache_lookup_seconds/analysis_attempt_finished_at。

## 源码明确的执行次序

`data/news_investment_service_v1.py:run` 已将新闻collect与初始preview用2线程并行，不能再把两段相加估计收益。两者完成后才构建positions/sources并命中模型缓存；随后无条件再次完整preview。这是当前缓存路径最大的**结构性重复候选**，但不是已测得的全部54.23秒归因。

`data/news_desk.py:collect` 仍按SOURCES逐一请求，然后发行服务capture，再Sandisk capture。每个HTTP使用有界超时；这是新闻内部串行网络链。来源之间可以独立并发，而同一发行服务的列表→正文存在依赖不能乱序。现有job没有保留本次完整source_receipts/各调用monotonic耗时，无法计算某源占比。拒绝按timeout上限猜实际耗时。

preview经 `data/news_investment_composition_v1.py` 调用 observed_daily.preview，包含账户/目标快照、证据构建、报价、风控、journal及最终有效性复查。`data/strategy_observed_frontier_daily_admission_v1.py` 的重复source/account checks用于防止IO期间过期，不能当冗余删掉。`saved_frontier_daily_composition_v1.py` 还存在至多一次分钟报价重采路径；本job未给出minute_recapture，不能推断本次有60秒等待。

## 建议最小改动与风险

1. **先补阶段计时，不动交易规则**：给并行capture/initial_preview分别记录开始结束、source_build、cache_lookup/model、final_preview、final_checks，保存当前尝试与缓存原receipt分开的字段。使用monotonic记录时长；UTC仅审计时点。避免记录完整私账或密钥。测试缓存命中当前耗时与旧receipt时间不会混淆。
2. **缓存命中才考虑复用初始preview**：只在缓存答案重新验证成功、账户/目标/新闻generation/sourcefingerprint未变、原preview全部报价与risk仍未过期、生成域与签名完全一致时，走已有最终纯校验；任一不满足则仍fresh preview。绝不能直接省掉第二preview或延长quote TTL。因初始preview与新闻并行，新闻采集慢时它可能已经老化，实际收益不能事先保证。应注入时钟测试边界同刻过期、账户更改、目标更改、新新闻、risk变化均拒绝复用，并确认不建立订单。
3. **新闻独立源有限并发**：最多2–3个来源任务，保留每源超时/最大正文/请求数与原始receipt；完成后单点写observations、稳定排序。不能并发多个同缓存写入者造成generation漂移。错误源不得静默当完整覆盖。先测采集耗时再决定是否值得实现。

优先级是计时与缓存路径的严格复用候选。此审计不建议自动定时全量复核：减轻延迟与及时发现是两回事，现工具仍是点击后采集，没有证明能在价格先动之前发现新闻。原目标里的及时投资辅助仍未被114.96秒缓存回放证明。

## R23实测后的决策更新

一次实际缓存复核已记录阶段耗时：采集9.96秒与初预览54.65秒并行，组装0.005秒，缓存查询0.045秒，后预览32.85秒，最终校验2.19秒，总计至结果就绪98.53秒，账户不变。没有新增推理。此单次差异不能宣称整体性能提升。

只读审查发现现有纯校验接口不能证明初始快照仍等价：风险存储、限仓、停牌/公司行动及执行状态的完整重验嵌在preview中。缓存只绑定模型输入，不能替代这些检查。因此本轮不实现跳过后置preview，也不延长报价期限。

已单独部署R24修复运行中状态查询等待账户锁：RUNNING只返回三项非金融进度，完成仍全量校验。用Event阻塞上下文的测试确认进度不等待；完成后账户改变/过期均拒绝。它改善进度可查询性，不声称模型或行情计算提速。

针对V27实际85个源码pin，双读170次与同绝对路径单读85次各交错测3轮，中位耗时0.08287秒与0.04586秒，每次仅省0.03701秒。未构造服务、调用账户、联网或测整个版本校验链。这个收益不足以解释preview耗时，停止该优化方向，不为小比例数字继续加补丁。证据在本地`tmp/news_source_gate_profile_20261028/v27_samepath_benchmark.json`。
