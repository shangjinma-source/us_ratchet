# 隔离三时点接线合同

D=原账本 effective_at，含义始终是股份分发；Q=报价单位切换；B=实际可交易时间；C=原账本 broker_confirmed_at（已知/确认时间，不等同 B）；K=独立实际可交易凭证的观察/接收时刻。

固定约束：D<=Q，D<=B<=K<=now，now>=C 且 now>=Q。C 与 B 不作普遍先后约束。只有未来预告不能作为实际已到账证明；必须有单独、绑定原 action hash 的实际可交易证据与 K。每个时点明确来源引用及原文 hash，旧账本/签名对象/receipt 不改。

价格、风险历史和公司行动价格事件匹配使用 Q；股份数量按原账本 D。日线切换 Q 仅允许会话开盘或非交易时段且落在下次完整报价会话前；盘中混合单位日没有细粒度来源时拒绝，不把整日当新单位。

执行最早为 max(Q,B,C,K)。报价 observed_at>=Q；实际到账证据不可在未来。原拆股后账本后缀已有成交 executed_at 在 [D,Q) 不能自动追认为新单位，必须拒绝等待对账。现金/真实成交续接仍通过 immutable transition 的账本前缀验证；任何额外未准备行动拒绝。

需成组覆盖：native/risk/history/preparation；原始历史reader及补采坐标；provider行动匹配和单位审阅；quote、限价、scoped preview。生产未激活，凭证内容一致性不等于独立认证。


## 已实现隔离组装与测试边界

实现文件：coordinates（native/risk/history/preparation）、action_review（原provider事件哈希/ratio/receipt校验保留）、daily_evidence（固定ledger前缀/当前revision及timing）、daily_composition（真实quote/action/limits与原差额算法组合）。没有修改生产原模块，也没有重写签名target/proposal或旧receipt。

Q对应价格边界由同一固定calendar确定为第一个open>=Q的完整会话；Q盘中拒绝，Q恰收盘/盘后映射后续会话，周五盘后→周一。calendar hash、日期与纽约开闭市日期、会话顺序都检查，reader要求实际calendar与timing bundle完全相同。原Q仍用于报价时间检查，不能把派生会话开盘冒充发行人原披露时点。

Agent session26408：4项综合测试，93.571秒，exit0。包括两个历史basis；C早于B与C晚于B；前夜D/翌日Q实际A2→16报价卖出；正现金、零现金、缺买行情、现金更新、真实成交后刷新六路径；K尚未达到/未来预告拒绝；[D,Q)成交对账拒绝；盘中Q拒绝；周五收盘及盘后→周一50/51精确历史投影。之后仅增加calendar纽约日期一致性防护，最终相同源码完整回归由根线程执行并另记结果，不把前一版本测试冒充最终源码全通过。

测试原始行情、身份、时点凭证和账户是合成夹具；复用真实SQLite ledger/archive/风险准备、市场解析、行动审阅、限价、差额；网络禁止，未调用真实AI/账户。不存在对供应商或券商凭证的独立真实性认证。

原 `split_frontier_supplement_20261105.py` 仍保持旧同钟语义，不能直接传三时点。补采三时点的新候选由独审agent独立接线，须其完整受控capture测试通过后另计；本报告不代其验收。生产自动接线/配置/部署、真实券商时点凭证与真实供应商basis仍未完成，不声明原Goal全部完成。

根线程最终源码独立复核：`D:/python/python.exe -m unittest discover -s tests -p test_split_three_clock_daily_20261105.py -q`，session1152自然退出0，4项综合测试77.059秒全部通过，包含新增日历日期校验。此结果仅证明上述受控链路，不证明真实来源认证、生产部署或策略经济收益。
