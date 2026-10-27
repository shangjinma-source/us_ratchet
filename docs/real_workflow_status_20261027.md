# 10月27日18:33真实流程与调度核对

本轮全部为读取：本机GET、配置SHA核对、调度读取及不带execute的来源任务dry-run。没有预览请求、外网行情请求、新闻模型调用、账户写入或调度变更。

## 当前服务

- 8010有监听进程；首页、账户、月目标、新闻页均GET200，OpenAPI标题为us_ratchet。
- 活动配置为`research_contracts/frontier_runtime_20261027_v27_r13/server.json`，配置SHA正确，77项源码pin全部匹配。
- 账户revision与R13部署前凭证一致，现金确认标记有效。此项仅证明现有状态，不新增真实现金保存或成交写入验收。
- 私人响应和校验记录保留本机`tmp/real_workflow_status_20261027/`，不上传账户或页面内容。

## 一项旧链故障，不能以任务退出码代替业务状态

`UsRatchet-DailySource-Evidence`最近运行2026-10-26，退出码3。对应`data/local_scheduler/dynamic-daily-source/1dafda5dea2b4e64b47f6a0a74b7b784.json`为NEEDS_RECOVERY/DYNAMIC_CAPTURE_FAILED，2次HTTP。下层MRNA采集记录明确RSS_PUBLICATION_TIME_INVALID：收到的feed中两条17:00UTC公告晚于13:10UTC接收时间，触发全feed时间校验。

本轮执行现行CLI但不带`--execute`，得到WAIT_PREVIOUS_SESSION_EVIDENCE/DYNAMIC_PREVIOUS_NOT_ADMITTED、0HTTP；退出码为0不表示已恢复。旧失败terminal仍保留，未改写或重试。

V27构建器替换旧reader为SavedFrontierLiveReader，后者按独立15分钟槽采集，不读取旧逐日前日terminal；既有R5/R7实际盘中READY证据另见[intraday验收](intraday_acceptance_20261027.md)。这解释旧任务失败与V27可用可以同时存在，并不证明所有间接消费者已审计。旧配置/源码仍参与继承校验，不能删除。暂不为恢复这条链重新取历史资料；退役调度需要先完成全部消费者及替代任务覆盖检查，当前仍保留任务。

其他四个UsRatchet任务最近退出码0，但不据此认定业务验收。最新月底业务记录10:29:02UTC明确WAITING_SESSION_CLOSE、0HTTP、account_writes=false、target_created=false。CurrentAdvice-Followup实际指向`run_local_current_followups_v1.ps1`且文件存在，审查中误读成follow_ups导致的缺失疑点已排除。

## 尚未完成

- 用户下一笔策略内真实成交的持仓、现金再确认和刷新幂等验收。
- 月底收盘资料准备、新月资料采用及正常现金按钮生成新月目标。
- 新闻实际影响买卖、完整历史经济对照、保持年化降低回撤，仍独立未完成，见[新闻机制审查](news_semantic_review_decision_20261027.md)。

本轮没有重新执行盘中报价验收，也未证明现金保存或未来调度成功。不得引用旧交付首页的R7/R9待授权描述为当前部署状态。
