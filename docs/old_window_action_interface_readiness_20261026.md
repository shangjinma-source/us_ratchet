# 2024–2026 行动接口恢复清单

只读源码审查，未改已钉 hash 源码、未重复测试、未跑经济搜索。完整路线必须同时满足执行 kernel、provider、独立 reviewer，不能因 kernel 有一个分支就称已接通。

|行动|现有实际能力及文件行号|恢复后处理|
|---|---|---|
|普通 USD 现金股息|`backtest/historical_dividend_frontier_research.py:114` 传入事件；`historical_dividend_next_open_book_research.py:165` 按交易前持仓计提、`:404` 支付日收盘入现金；`historical_dividend_independent_review.py:59` 独立核字段与日期。|可直接接已审核事件：event_id/security_id/ex_date/payment_date/amount_per_share/withholding_rate/assumption/currency。未知支付日保持应收；同日股息与行动冲突仍拒绝。|
|同 SID 普通拆股，转换后持仓及订单均整数|kernel `historical_dividend_next_open_book_research.py:280`；reviewer `historical_dividend_independent_review.py:43`、`:123` 独立转换持仓、订单、decision_mark，并核 provider_actions 与 actions 一致。|可接已核事实与 source_references。比例可以是反向，但结果必须整数；实际零股不支持，不能自行舍入或生现金。|
|SMCI 跨 SID 拆股；HON 跨 SID＋反向拆股|kernel `historical_dividend_next_open_book_research.py:282` 有 split_identity、successor 冲突检查和旧 SID 终止；reviewer `historical_dividend_independent_review.py:44` 只接受 type=split。|需适配独立 reviewer、provider 身份承接及峰值单位，再做小非空组合测试。当前不能为通过审核改写成同 SID split。HON 分配还须独立处理。|
|ILMN/GRAL、HON/SOLS/HONA、WDC/SNDK、CMCSA/VSNT 分拆|kernel `historical_dividend_next_open_book_research.py:172` 接 distribution_events，`:394` 估值未交付权益；与其他未结资本并存会拒绝。reviewer `historical_dividend_independent_review.py:40` 全拒绝 distribution_events，`:158` 拒绝权益残留。|需要扩独立权益账审计及实际交付接口；已核价格坐标不等于分拆股数或到账认证。实际暴露时 gate。|
|SPLK 纯现金并购|kernel `historical_dividend_next_open_book_research.py:314` merger 转应收、终止旧股并取消订单；reviewer `historical_dividend_independent_review.py:44` 不接受 merger，`:158` 要求普通 receivable 为零。|需独立现金并购应收／支付审计，不可当普通股息或真实卖出。|
|ANSS 现金＋SNPS 股票并购|kernel 独立参数 cash_stock_merger_events 在 `historical_dividend_next_open_book_research.py:178`、`:370`、`:379` 可条件转换及估值未交付权益；普通 actions 中 type=cash_stock_merger 在`:307` 对暴露明确拒绝。reviewer`:40`拒绝混合事件。|必须走正确独立参数并匹配事件时序；现有条件 end-session 路径不能直接冒充 ANSS 盘前完成。需适配审计、SNPS 权益估值与交付／零股；使用最终199.91＋0.3399事实。|
|WBA 现金＋不可转让 DAP|上述普通 cash merger 只有 share_cash，无 DAP 专用估值／交付结构。reviewer 也不支持。|必须 gate；不能把 DAP 当0、按3美元上限定价或冒充普通可交易子股。已核事实见 [生命周期文档](old_holdings_lifecycle_gate_20261026.md)，价值及实际到账仍未知。|
|SIRI 重组／反向拆股|普通整数 split 可处理单位；没有由该能力自动获得的旧新证券重组身份认证。|先补精确旧新身份、换股及零股事实；不能只用 provider 0.1 解禁。|

已有有效测试定位：`tests/test_historical_dividend_ledger_research.py:16/23/29/40` 覆盖交易前持仓、幂等、支付守恒、未知支付日；`tests/test_historical_dividend_frontier_research.py:27/32` 覆盖无股息一致及已支付现金影响配置；`tests/test_historical_dividend_independent_review.py:59/65/73` 覆盖非空拆股＋卖出＋股息＋买入、错误比例和证据、零股拒绝。`tests/test_historical_dividend_next_open_book_research.py:57` 是 successor 同日股息冲突拒绝测试，不能作为跨 SID 全路径已审证明。

最短恢复顺序：先接事件已审核、无复杂权益的实际暴露路径；保存未支持事件的准确断点。按实际命中的行动扩独立审计及非空小测试，避免把所有未选候选的复杂事件都当成启动前必需工程。
