# 同11月名单注册采用价值评估（只读，2026-11-06）

建议：本轮不为补一个“采用成功”标签而重发同11月名单。现有base已是正式11月ROA十股；真正功能缺口不是缺这次同名单登记。

## 已核事实

- 当前active SHA `a6dae610cad9c8b013a4bbac0445788463d2eeb760a9e7e22aee20b35d1d1e60` 与已准备registration expected_active相同；新配置只追加monthly_selections[2026-11]，其余roa/base/pins均相同。
- 对照`tmp/roa_november_signal_20261106.json`与真实回放月包：selection、十个security_id/ticker/issuer_id、weights完全相等；decision仍10/30、财务截止9/30。运行包selection_id为b852092e9e1f97b9966765c8e9eb26dcea48f120f449ed861e8d932eae23859b。
- `RoaDailySignalProvider.__call__`增加monthly_selection_id和原始源绑定，将改变signal_id；`_read`仍以固定_base.signal_id为基准，故不会重置QQQ历史或其SMA200状态。
- 当前生命周期version2，decision/risk/last_close均未设置，已有两个11/6 OPEN计划均targets/materialized_revision=None；读取新signal后plan会增加一个新ID的STRATEGY_ACTIVATION OPEN，新窗口仍22:30–22:45。不会凭此产生账户成交、持仓或现金变化，但旧前端预览身份失效、生命周期文件将正常增加计划记录，不能要求生命周期字节不变。
- 若已经materialized才做，同月同risk不会仅因signal_id变化再分配；但这不是本轮当前事实。发布前必须重新检查，不可依赖此审计过时快照。
- 真实回放月包与注册配置在tmp，不应直接作为长期生产依赖。持久化会改变源路径和selection_id，必须重新发布/登记/gate；不能简单移动目录令旧hash路径失效。

## 若另行决定采用，最小完整步骤

1. 将同一已核输入按不可变持久目录发布，保持selected、weights、decision、financial_cutoff完全一致，生成新receipt与registration；不用重选策略，但路径/身份变更要承认。
2. 重新核当前active、实际账户完整投影、未结订单、life是否已materialized；记录源码/进程PID/命令及回滚active原bytes。若交易窗口已开始，避免中断实际挂单，另择受控时点。
3. 用`adopt_roa_monthly_registration(...,execute=True)`执行受控采用；其内部已调用`prepare_roa_monthly_publication`完成当前及拟发布完整V34 gate，并在唯一锁下做最终gate、预期active复核和原子指针替换。无需先额外运行一遍相同publication检查；若此前单独预检过，采用时仍须重验。该结果仅磁盘切换待重启，不等于上线；排他要求其他发布者遵守同一锁，不能声称文件系统替换是系统级CAS。
4. 按正式`start_service.ps1`流程精准停确认的原服务并只启动一次，等待完整初始化；核/api/strategy-roa/config和snapshot、静态资源、newsworker、期望month selection来源；账户全投影前后相同，策略经济字段相同。新life计划ID/版本允许按上述预期变化，不能误当账户写入。
5. 已安装ROA月度scheduler的request固定旧active SHA，不能留旧descriptor假装可运行，也不能运行时偷更新hash。将request仅受控重绑新active并独审，重新生成完整sourcepins descriptor，检查已存在新任务的正式更新入口；原安装器对不同参数会拒绝覆盖，需另行受控更新新ROA任务，其他金融任务保留。
6. 失败时先核磁盘/进程实际状态：只有active仍等本次next SHA才允许恢复精确rollback bytes，保留新lifecycle审计历史；再重启旧配置一次并验账户/服务。不可覆盖他人后续发布，不能将未知切换失败当未发生。

## 验收口径

本轮已有真实历史月包和正式publication gate通过，足以证明准备/校验阶段，不冒称已经验证生产采用。当前base已实际提供11月ROA建议；12月真正新名单采用仍待真实资料和事件。为同名单重启/重绑调度只增加操作风险而无投资功能收益，本次建议不做。
