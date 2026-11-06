# 候选目标接入正式 HTTP 验证

仅临时 SQLite、FastAPI TestClient 和合成证券/金额，不访问 8010 或真实账户。新增 `tests/test_target_account_http_bridge_20261106.py`，1 项端到端测试通过。

实际运行正式 `api.strategy_account.create_router` 和 `api.strategy_frontier_daily_preview_v1.create_router`，账户初始化、成交记录、现金确认、未成交委托全部走 HTTP 公开接口，候选计算复用真实 preview_scoped_account/差额引擎。身份 resolver 和冻结目标为明确合成输入，绑定包装为测试 harness，非生产认证 provider。

新增的关键覆盖是未成交买单占款：合成总现金1000、已有旧仓3股，NEW已挂4股各100；重新确认可用600后，目标13股，新增只买6股并建议卖旧仓3股。不能把已挂4股重复买入，也不能把预期旧仓卖出款提前支出。整个预览账户不变。未重新确认占款时 HTTP 409；旧revision、错误proposal、客户端注入weights均拒绝。

明确实际接入失败点：直接把原候选返回值送给正式 v3 router，会因缺 target_id/proposal_id 返回绑定失败、HTTP 409且new_orders为空。本测试切换为不补绑定的模式，真实复现 FRONTIER_RESPONSE_BINDING_MISMATCH。这证明候选尚不能原样上线；测试 harness 补字段只用于验证账户占款路径，不是新策略认证接入。

下一步须由正式经济候选的 server-owned 冻结目标服务生成独立target/proposal身份，绑定策略合同、账户revision、信号及来源，并经过现有快照末尾重验；不能简单把客户端ID复制进响应就宣称上线。此次不改生产经济规则，也不以模拟接口通过替代真实用户成交验收。
