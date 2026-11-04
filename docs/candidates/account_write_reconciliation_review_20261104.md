# 账户写入成功后返回失败：已复现，补丁未部署

2026-11-04。正式 `api/strategy_account.py` 在 store.append 提交后调用 project；若 project 抛出 ValueError，HTTP异常处理将其返回为422 BLOCKED。临时真实SQLite复现结果：接口422/PROJECTION_UNAVAILABLE，但可用现金已经100，且存在一条CASH_CONFIRM。未读写生产账户。

现有前端对503或显式write_may_have_occurred/reconcile_before_retry会进入待核对状态，但普通422不会；账户版本校验及成交event_id仍提供防重保护，所以此问题不能描述为已发现重复成交。缺口是后端把已提交但返回失败误报为普通拒绝，用户反馈和恢复路径不准确。

完整候选 `strategy_account_write_reconciliation.py` 保留原规则，只增加提交后投影异常包装，并将其及写请求未知异常返回503/RECONCILE_REQUIRED、两个核对标志、no-store。合法输入错误仍422。不得回滚或恢复真实账户数据库来处理这种响应失败。

新增4项临时HTTP测试全部通过：初始化、现金、成交在提交后返回失败；GET核对与原event_id/原revision重试返回同一结果，完整账本不变；无效输入仍为确定拒绝且不建库。原账户API4项在进程内替换为候选后回归通过。无外部网络、模型或下单。

尚未部署：活动V30沿base引用向下24层，账户源码pin位于V6配置 `research_contracts/unified_server_identity_closure_20261021_v10_v5/server-level-4.json`；该层还有preparation及daily_configuration等引用，不能仅改最外层hash。下一步需检查这些引用的源码约束，准备独立完整配置链及回退材料，验证正式组合后统一切换。当前生产文件、活动配置、服务和真实账本均保持原样。

本轮仍属于修复准备，不宣称线上缺口已消除。前面的只读预览测试不覆盖此类写入后响应失败；修复部署后还应核对正式路由、源码pins和新闻任务生命周期。

后续状态：同日已完成正式配置链和部署，见 `docs/account_write_reconciliation_deployment_20261104.md`。上文保留为部署前研究记录；测试现在直接导入正式账户模块。
