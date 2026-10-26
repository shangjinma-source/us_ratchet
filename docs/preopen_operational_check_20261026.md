# 10月26日开盘前运行核查

核查时间：北京时间 2026-10-26 17:44—17:52。此记录是开盘前检查，不代替盘中、真实成交或换月验收。

## 已核实

| 项目 | 实际结果 | 含义 |
| --- | --- | --- |
| 8010 生产服务 | 现有 PID 25688 正常监听；账户接口 READY | 服务可读，未重启 |
| 账户现金状态 | cash_confirmation_valid=true、execution_ready=true、orders_submitted=false | 现金确认有效；没有提交订单，不代表盘中报价已验收 |
| 策略 | 活跃配置仍指向 frontier_runtime_20261025_v27_r1 | 本轮被否决的趋势候选没有上线 |
| 真实月度更新 | 17:44 返回 WAITING_SESSION_CLOSE，account_writes=false、target_created=false | 等待真实收盘，不是已完成月底发布 |
| 登记纸面验证 | 17:36 返回 WAIT_REGISTERED_START，account_writes=false | 等待登记起点，不是完成策略实盘验收 |
| 当前建议跟踪 | 06:15 返回 WAIT_OBSERVATION_CLOSE；101 条已核验，250 条未到观察期，blocked 为空 | 已到期部分有结果，其余不能提前算成功 |
| 今晚盘中验收 | 当前聊天心跳 ACTIVE，10月26日22:05，仅一次 | 已安排；没有真实成交时仍不能完成成交承接验收 |

生产活跃配置 SHA256：`cf12f40148e3a95db8016f953b45be80163a3e227d9cea2668eb97de9f46900d`。

## 已处理的历史快照统计问题

`us_ratchet_advice_snapshot_audit` 最近退出码为 2。完整扫描确认 79,047 条记录全部有效，但侧车统计为 79,045 条；差异为两条计数，不是损坏快照，也不能据此判断 V27 当前建议链路失败。

使用已有 `scripts/advice_snapshot_audit.py --repair-meta` 重建统计文件，修复报告确认计数一致、无无效记录。原始日志仍为 2,566,212,007 字节，修改时间仍为 10月24日03:50:18；本轮未修改日志、账户、策略或定时任务。修复前统计文件及报告已保存在本地 `tmp/preopen_operational_audit_20261026/`，私人数据不提交 GitHub。

历史成因尚不能确认。现有写入流程的追加和统计更新分开，存在并发或中断窗口；本次不据此改动冻结的生产代码。若复发，应凭新证据修复写入一致性。

17:50独立只读复验通过：`repair_meta=false`、`ok=true`、`sidecar_consistent=true`、无无效行，命令退出0；当前 `data/advice_snapshot_audit_latest.json` 已更新为此复验报告。Windows任务自身的历史Result2仍是上次运行状态，不能说已重新运行该任务。

## 验收边界

另有旧 `us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar` 任务在10月24日返回2。其旧10路径影子研究与当前V27账户及发布链分离，最新保存结果仍止于9月25日，不能充当10月24日运行证据。静态激活校验通过，但当次异常仅输出stderr，缺少持久化诊断，精确失败原因未解决。本轮没有重跑该研究任务或修改其计划，也不能把该失败解释成正常等待开盘。

今晚22:05检查真实盘中建议；成交承接等待用户实际策略成交；月底选股等待10月30日美股收盘；新月换仓等待11月2日适用交易时点。

研究方面，两段完整基准及唯一固定趋势候选已经核验，候选因后窗年化明显下降而否决。保持年化并降低回撤仍未达成，不能将 Goal 描述为只剩等待开盘。详见 [策略结果](long_market_trend_result_20261026.md)。
