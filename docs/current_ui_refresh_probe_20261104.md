# 2026-11-04 实际页面刷新与附属读取对照

在当前8010正式服务（PID42172，news_post_scope_20261104/config-29.json）上使用隔离浏览器点击实际现金按钮。现金CASH_CONFIRM请求被本地拦截并返回读取快照，没有写真实账本；除preview以外的非GET被阻止。三个捕获均确认账户前后相同、建议WAIT_POLICY_REVIEW_SESSION。不得据此称真实保存、盘中建议、AI判断或成交承接通过。

| 测试浏览器条件 | 初始建议读取 | 点击后的建议读取 |
|---|---:|---:|
| 原页面 | 27.034秒 | 53.845秒 |
| 拦截估值和最新图表，但保留图表回退 | 23.623秒 | 64.245秒 |
| 拦截估值、最新图表及回退图表 | 48.634秒 | 23.065秒 |

第二轮返回503后触发target/bars回退，两项分别27.005秒及41.502秒，不能将其当成无图表对照。第三轮初始读取可能仍与此前服务器正在完成的请求重叠：关闭浏览器或中止HTTP并不证明后端工作停止。仅三个顺序观测不足以量化稳定提速倍率。

代码证据：RollingMonthlyRuntimeRouter.snapshot_operation持有共用RLock，valuation受该scope包装；FrontierDisplayBatchV1.contexts以及历史图表也读取同一路由。index.html在初始建议后启动自动估值及图表，用户紧接着点击按钮可能与其竞争。后续候选应优先管理非关键展示请求的启动时机，不放松行情期限、账户版本或源文件校验，也不能只abort请求就宣称释放了后端锁。

目视正式页面截图确认当前为四列布局：股票、持仓到目标、今日建议、原因与AI复核。WAIT没有展示可执行订单。既有review_daily_ui_capture_v3复核报WRITE_SCOPE：新增scheduled-earnings/refresh被拦截记录为unexpected；其下层仍假设旧七列DOM。必须更新捕获/复核协议，分别记录预期被阻止的日历或AI请求与未知写入，保留真实账户保护和当前四列表格的独立核验，不得删除失败记录直接宣称通过。

本地私人证据：tmp/ui_acceptance_20261104_2044、tmp/ui_acceptance_20261104_without_auxiliary、tmp/ui_acceptance_20261104_without_all_auxiliary。截图与账本内容不上传Git。临时隔离脚本tmp/capture_daily_without_auxiliary_reads.cjs不是生产代码，也不是最终验收器。
