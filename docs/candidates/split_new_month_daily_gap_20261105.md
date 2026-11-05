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

## 新月执行资料缺失已修复

真实生成目标后调用 `monthly.execution_provider`，复现 `MANIFEST_SOURCE_CHANGED`：执行路径只传 manifest，而新增月度单位审核需要完整训练资料。工厂现按原 pins 重读完整资料，并对传入 manifest 字节、hash 和历史参数逐项校验；不修改冻结目标、不重新选股、不放松源审核。

`test_split_monthly_execution_20261105.py` 通过真实目标生成、受控完整分钟行情、实际 action review 与限价计算，验证 B 使用 new 单位、账户未变；篡改 manifest 或历史参数分别拒绝。原选股 fixture 只有一根分钟 bar，曾被实际限价检查以 NONCONTIGUOUS_OR_FUTURE_MINUTE 正确拒绝；本测试补足受控原始分钟序列，未绕过检查。

最终验证：execution 1 项 0.721 秒、原 monthly factory 2 项 3.579 秒，均 OK。仍未证明新月完整 daily signal reader、受保护 HTTP 建议及生产上线。

## 原日执行桥不能直接承接新月工厂

实际诊断用真实 factory 生成目标，将该 provider 子类 `_assemble` 临时替换为必抛出的审核探针，再调用现有 `strategy_split_daily_execution_bridge.DailyExecutionBridge`。探针调用次数为 0，执行最终在基础实现报 `SPLIT_REVIEW_EVENT_OUTSIDE_INTERVAL`。所有对象和数据库均为临时合成资料。

原因：桥内显式调用基础 `StrategyAccountEvidenceProvider._assemble`，绕过工厂子类新增的完整历史审核、三时钟校验及行动查询窗口扩展。即使工厂直接 execution 已通过，不能据此宣称经过日执行桥也通过。

后续分工：独立 native reader 验证新 proposal 的原生数量、来源、单位与新月风险 epoch；独立 native execution bridge 保留实际 provider 子类审核和冻结目标/lineage。两者组合后再测 HTTP，当前不部署。

## 固定日历延长

新 native reader 的原 timing calendar 可能只覆盖训练结束日。新增 `split_calendar_extension_20261105.validate_calendar_extension`：仅允许完整保留历史 sessions 前缀后追加日期，日历其余字段必须完全一致；全部会话校验纽约日期、开始结束顺序、无重叠及日期递增。原 timing hash 和拆股报价单位边界不重签、不重算。

独立测试 1 项 0.012 秒通过：追加和原样允许；改历史、删除、前插、重复、跨日期及改市场拒绝。该测试仅证明扩展规则，native reader 接入与其完整源测试仍由同轮任务继续验证。

## Native reader 拒绝边界

独立 `test_split_native_daily_bindings_20261105.py` 在实际 factory 目标与源归档上验证：重新 hash 当前复核仍不能替换目标原有 timing；真实临时现金事件后旧复核 revision 拒绝；目标生成后增加新的拆股行动不能沿用原目标。三者均在风险写入前拒绝，未生成成功信号档案。session41457：1 综合测试17.697秒通过。首次测试的新行动时点晚于临时 store 时钟，被 FUTURE_SPLIT_CONFIRMATION 正确阻止；仅将测试时钟推进到测试当前时点后重跑，未改产品检查。

组合联调随后发现原 source fixture 曾对带 view 附加字段的 target 重建 proposal，未使用真实 proposal store 中的编号。该 fixture 正在修正为原 monthly.current() 和 view.require_proposal；上述边界需随修正后的完整组合组再次确认，暂不将这次独立通过当成端到端完成。
