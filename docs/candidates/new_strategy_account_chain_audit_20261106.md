# 新策略接入准备复核

本轮只读活动配置，隔离 SQLite 测试；没有重启、账户写入或生产源码修改。

## 当前实际版本

活动指针为 `research_contracts/shared_snapshot_20261106/config-26.json`，文件 SHA256 实算与活动指针一致：`1760d0f0d528132470220e6318bf8ba40d3858951e33068875ebebf5b56c202d`。schema 为 RESTART_PERFORMANCE_UNIFIED_PREPARATION_V33。V33 是服务组合版本，不能代表经济策略已替换。此前 deployment_readiness 文档的 notice_scope/V32 路径是历史快照，以本次读取为准。

## 本轮修复的覆盖缺口

既有 `tests/test_target_account_bridge_20261106.py` 仅测试一次现金、少量旧仓。`tests/test_cash_button_real_ledger_browser.py` 虽覆盖前端增减现金，但 preview 是 synthetic，不能把它视为新目标算法与实际差额引擎的贯通证据。

新增隔离真实账本测试 `test_cash_increase_decrease_rebuilds_targets_from_real_ledger`：合成旧证券持仓，现金依次 1000→3000→500；真实 StrategyAccountStore 保存 CASH_CONFIRM，候选按新权益生成目标，再调用实际 preview_scoped_account/差额引擎。目标依次 24→44→19 股，新购受当前现金限制依次 10→30→5 股；旧仓卖出建议始终按实际持仓产生，未卖出资金不提前用于买入。每轮无挂单、持仓与账本读取完全一致、不同 revision、candidate 始终非生产非可执行。使用通用合成证券和金额，无私人账户 fixture。

`D:/python/python.exe -m unittest discover -s tests -p test_target_account_bridge_20261106.py`：2 项通过。原用例继续覆盖过期、revision 拒绝与空目标防御卖出。此次没有伪造历史新策略入场或初始 R。

后续补齐同候选桥接的成交闭环：在隔离库使用公开 store.append(DIRECT_FILL) 录入建议旧仓卖出，合成卖出收入 300、费用 2，effect 净现金变动 298，旧仓归零。实际账本契约不自动把旧现金确认改成新券商余额；成交后旧现金失效，候选明确拒绝 CASH_RECONFIRMATION_REQUIRED。再用公开 CASH_CONFIRM 确认合成余额 1548 后，新建议仅买 NEW 15 股，不再卖旧仓。相同成交 event_id 分别在成交后和重新确认现金后重试，均不增加事件、改变 revision、持仓或现金。扩展后同一 2 项测试继续通过。这是隔离模拟成交与真实接口验证，不是用户真实成交验收。

## 尚不能称为正式上线的接口缺口

候选 `preview_target_weights` 输入账户 revision、权重、报价、限价、信号有效窗和合同哈希；只输出研究目标及差额。没有认证信号 provider、经济准入或正式 target_id/proposal_id，因此不能直接给正式现金按钮使用。

实际 CurrentPreviewV1 / BoundPreviewSnapshotV1 依赖 monthly snapshot_operation、current target、proposal_id、月份及 compact 投影；快照前后再次验证 source pins、账户与目标不变。新经济内核需保持这些保护并替换目标生成源，提供独立策略 epoch/合同哈希绑定，更新前端当前建议绑定和真实版本显示。日线突破/入场 R 类型不能强行套用固定月权重接口，其旧仓迁移规则也必须独立定义和验证。

因此目前仅证明真实账本→新权重目标→现金约束差额的隔离链路，未证明正式前端→合格新经济内核→实际账户完整端到端；经济候选未确定时不构造假的上线接口。

## 回滚材料

当前共享估值快照发布材料位于本地 `tmp/shared_snapshot_deployment_20261106`，含 previous_active.json、previous API/web 文件、next 文件、changed_files.json、deployment_integrity.json 与私有前后快照。它仅覆盖该次 UI/API 发布，不是未来经济策略的现成回滚包。

新策略发布前必须从届时活动版本重新冻结整条配置及源码清单、生成新策略专用回滚包。回滚源码和活动配置，不回滚真实账户数据库，避免覆盖发布期间发生的用户成交或现金确认。当前测试未替代真实成交验收。
