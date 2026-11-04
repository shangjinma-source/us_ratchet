# 拆股候选当前边界复核（2026-11-05）

本轮只读复核与重跑现有隔离测试，没有新增adapter、生产改动、真实账户写入、券商到账认证或部署。旧 `sndk_publication_and_split_review_20261104.md` 的“准备包到实际差额”是较早状态，后续已实现的候选链见 `split_preview_bridge_20261104.md`，不能据旧段重复开发。

实际执行以下命令，各自均通过：

```powershell
D:/python/python.exe -m unittest discover -s tests -p test_split_cash_fill_workflow_v1.py
D:/python/python.exe -m unittest discover -s tests -p test_split_unit_review_v1.py
D:/python/python.exe -m unittest discover -s tests -p test_split_risk_daily_preview_v1.py
D:/python/python.exe -m unittest discover -s tests -p test_split_bundle_decision_handoff.py
```

外层2+5+1+3=11项通过；单位审核测试内还运行原正式审核5项回归，不重复计为11个外层场景。总命令约2秒。此前源码已有：

- 真实临时准备包、SplitStrategyAccountStore与风险转换→112股风险退出→模拟卖出→确认回款→刷新无重复卖出/买回；另测拆后买入、成本、事件幂等。
- 完整单位审核候选：行动捕获与已记录拆股匹配、旧单位/训练期内拆股/相关公告继续拒绝，生成审核再接月度资本输入。
- 保存风险→每日信号门槛→DailyExecutionBridge→实际采集解析/行动审核/候选限价→拆股scoped preview；风险退出仍优先。网络传输、身份/历史审核及信号均为明确合成夹具。
- 生产旧preview仍使用旧replay，遇SPLIT_CONFIRMED的EVENT_FIELDS拒绝确实存在；此项是确认未挂载边界，不是生产缺陷已修复。

对应现有实现：`docs/candidates/strategy_account_split_unit_review.py`、`strategy_account_split_scoped_preview.py`、`strategy_split_frontier_preview_service.py`、`strategy_split_daily_execution_bridge.py`，以及 `data/strategy_split_account_preview_v1.py`。不存在需要再复制一套同类adapter的证据。

## 仍未闭合的真实条件

1. 正式原始历史审核要求 `FULL_WINDOW_CONSTANT_UNITS_NO_ACTIONS`，原始close/adjclose与归一化序列一致。候选观察值转换不等于已证明供应商是否复权；不能清空行动或重写原文绕过。
2. 已记录行动与捕获行动一致只证明内容匹配。prepare/native transition及单位审核仍明确来源/券商认证false、不可执行；尚无本轮取得的真实券商可交易到账证据。
   后续认证还应区分发股时刻、行情单位切换会话和券商可交易到账；现 `recorded_split_review` 用已记录effective_at纽约日期匹配provider拆股日期，不能把发股日自动当下一交易日的报价切换时点。该合同问题尚未用真实资料闭合，本轮不修改或放行。
3. 正式每日evidence reader/composition、原目标/新目标与风险epoch、AI及跨月入口未成组切换；不能把基础月preview上线而绕过日风险。
4. 账户/目标/风险统一激活、旧进程退役和不回滚真实账户的失败恢复尚未验收。

以上为现有测试与源码的边界复核，不是新经济成果、不替代真实成交验收。此支线收束，不新增组合测试或重复框架。
