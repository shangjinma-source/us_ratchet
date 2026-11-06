# 真实成交迟录：有限恢复方案

本候选不修改冻结发布模块，不写账户、不推定成交。`roa_late_fill_recovery_20261106.py` 返回待应用的生命周期恢复提案，不能自行部署。

## 已验证的账本事实

`core/strategy_account_store.py` 保留并校验 SQLite `received_at`，要求实际成交 `executed_at <= received_at`。账户投影的 events 不暴露 received_at，但保留 executed_at；`core/strategy_account_ledger.replay` 可重建并逐项校验账户。现金确认不是资金流，也不参与本次持股历史推算。

收到迟录成交后，按真实 executed_at 重建每个历史 close 的持股。实现从已重放校验的当前实股反向剔除该 close 之后的真实成交；关联 FILL 从原 order 取 SID/方向，DIRECT_FILL 从原 payload 取。没有成交事件，即使建议目标九股也仍是零股。

## 最小生产接入前置条件

1. 每次收盘维护前保存受服务端保护、绑定 epoch/contract/hash 的生命周期 checkpoint 和当时账户 revision。不能用今天峰值倒造 checkpoint。
2. 保存或获取从 checkpoint 到当前已观察 close 的连续权威交易日、原始名义收盘价及证据；拆股/身份转换需要专用重放，本函数不偷偷默认股份连续。
3. 本轮只自动恢复未跨新的已 materialized OPEN 的区间。新月重置/新市场切换若已据错误旧状态生成真实目标，需要显式重审该目标；不可悄悄追改。
4. 迟录后重放 close，恢复峰值/pending/已完成退出；生成今日剩余建议时仍只用当前真实余额/持股，不将历史反事实订单当成交。
5. 应用前重新读账户 revision 与生命周期 digest，必须与提案一致；在同一受控服务锁内原子替换生命周期、采用当前版本+1，保留原 checkpoint 和恢复审计。任何变更重新计算，不覆盖并发事件。
6. 实际 fill 已记录而现金未重新确认时仍要求正常现金确认；恢复函数不代填现金。

当前发布模块尚未持久化该 checkpoint，因此这是明确可实施的恢复接口和回归，不声称迟录恢复已经上线。已有旧状态没有可信 checkpoint 时可利用完整历史维护记录重建，但不得推断缺失的开盘物化/峰值；该范围本候选拒绝。

## 合成验证

`D:/python/python.exe -m unittest discover -s tests -p test_roa_late_fill_recovery_20261106.py`

5项通过：迟录买九股后已有后日真实卖五股，恢复旧 close 仍是九股且保留开盘100→收盘75的止损；无成交绝不制造持股；未来收盘和缺价拒绝；跨后续物化 OPEN 拒绝；被篡改账户拒绝。所有测试使用合成账本，无私人账户写入，无策略回测。

## 正式独立 wrapper 已实现（尚未挂载）

`data/roa_close_recovery.py` 不导入 docs/candidates。`TrustedCloseRecovery.observe(session)` 由可信服务维护器调用，构造时固定账户 store、生命周期、私有 checkpoint 目录、权威日历与价格证据回调，无 HTTP/客户端文件入口。

首次维护在 SQLite `BEGIN IMMEDIATE` 与 lifecycle 共享锁内持久化观察前 checkpoint；网络取价在锁外。恢复应用时重新取得 SQLite 写保留锁、重验账户 revision/生命周期摘要/所有价格文件 hash，写先行恢复审计后原子保存生命周期。账户事务仅读并 rollback，不写资金或成交。新版本基于当前生命周期 version+1，重复已完成同 revision/state 返回 UNCHANGED。

`tests/test_roa_close_recovery_sqlite_20261106.py` 使用真实临时 SQLite 与状态文件，3 项实际通过；原5项纯回放测试已改为导入正式模块，也通过。新增集成尚未改冻结 composition/lifecycle，因此生产接入状态仍为待挂载。
