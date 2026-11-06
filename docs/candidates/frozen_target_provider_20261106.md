# 服务端冻结候选目标 provider

新增 `frozen_target_provider_20261106.py`，仅研究隔离、不启用生产。正式月目标存储验证 decision/target SHA 与月目标链，但其 schema 是 REAL_STRATEGY_MONTHLY_TARGET_V1，要求既有 decision、request、previous_target_id 和月内规则，不能把新权重合同假扮成原月目标。

最小新研究 schema 为 FROZEN_WEIGHT_TARGET_RESEARCH_V1，服务端固定文件路径及字节 SHA、策略 contract SHA、账户 ID；payload 内包含 account_revision、strategy_epoch、weights、marks、limits 和信号/生效/到期时间。复用正式账本 canonical 进行 payload digest。proposal digest 绑定该 target ID 与研究 proposal schema，client 仅可提供 expected IDs/revision，不能传权重。

每次预览核对文件 SHA、payload target digest、proposal digest、contract、账户归属/revision、预期 IDs，再核全部冻结报价身份、正价格与120秒有效期，调用已有 bridge。完成后再次核文件内容、账户完整状态、目标及报价到期时间，返回已核验文件中的 IDs。此处只对冻结单快照提供服务；账户或报价更新后必须由可信服务重新构建并批准新冻结文件，不自动沿用过期目标。

`tests/test_frozen_target_provider_20261106.py` 真实正式 v3 HTTP router 集成通过：有效10股差额，篡改weights导致文件SHA失败；仅重钉文件SHA仍因payload digest失败；错contract、过期目标/报价、错proposal均拒绝。无真实账户、网络、订单或经济策略修改。候选始终 executable=false / production_activated=false。

这补齐此前仅harness回显ID的缺口，但不是生产经济准入。来源/身份 resolver 证明、获准经济合同、可信目标构造及激活链、最新报价生成、AI联动和真实页面适配仍需由正式组合承担；当前代码不宣称这些已完成。文件SHA必须来自受信任部署配置，不接受用户提交SHA来绕过冻结。
