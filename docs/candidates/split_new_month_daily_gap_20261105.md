# 新月目标与拆股日建议衔接：尚未完成

当前检查确认，三时钟 daily evidence 和 daily composition 均以拆股前目标对应的不可变 transition 为准；数量来自 transition.risk_projection.target_quantities。它们不是新月原生目标的日建议实现。

已增加显式 original_target_id / original_proposal_id 校验。真实临时 SQLite preparation 和旧目标仍通过，替换任一绑定会以 SPLIT_TRANSITION_TARGET_REQUIRES_NEW_MONTHLY_PATH 拒绝，输入未修改。命令：`D:/python/python.exe -B -m unittest discover -s tests -p test_split_transition_target_binding_20261105.py -q`；1 项测试，3.733 秒，OK。

这项校验只使现有边界明确，不代表新月日建议已支持。下一步必须：

- 从真实 MONTHLY_SELECTION 生成的新目标和新 proposal 读取当前单位数量，不再次乘拆股比例。
- 原拆股 transition 仅验证历史迁移，保持绑定原目标；新目标采用自己的源码批准及行情单位证据。
- 风险参考以新月 epoch 初始化，保留上月档案；同月现金更新不得借机重置退出状态。
- 用真实两月选择输出接通 HTTP current / cash / fill / news，验证新 target、proposal、revision 一致，旧 AI 结果失效。
- 继续保留旧仓、未成交单、现金限制、报价单位和券商实际可交易时点校验。

候选改动未部署，未写真实账户，未改变 V27 策略或原定时任务。下一次执行批准必须使用修改后的 daily evidence 源码 hash；不修改旧批准收据。

## 新月风险边界已验证

新增 `tests/test_split_new_month_risk_20261105.py`，在真实临时 split-prepared SQLite 上调用现有 `apply_frontier_exit_packet`。新月目标为签名合成 fixture，并非真实选股器输出，因此只证明风险边界：

- 缺少显式月 reset 授权时拒绝，原风险状态不变。
- 有授权时采用新 proposal 原生股数，不再次乘 8；A 保留 unit-A8。
- 新月份状态重新初始化；上月价格历史与 split_preparation 内容、摘要保持不变。
- 同一新月数据再次调用，状态与有效目标数量一致。

验证命令：`D:/python/python.exe -B -m unittest discover -s tests -p test_split_new_month_risk_20261105.py -q`；1 项测试，5.379 秒，OK。现有风险计算可复用，下一步重点是原生新月 source admission / reader / execution 接线，不需复制一套风险算法。该结果不证明完整两月选择、HTTP 建议、真实成交或生产部署已通过。
