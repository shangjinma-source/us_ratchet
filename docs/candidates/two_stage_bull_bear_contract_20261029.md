# 两阶段执行完整牛熊对照：待主审冻结

范围：A所有新增买入缺口分两开盘（不再限新入金，不能称用户真实入金复现）；B只有纯cap增量卖出分两开盘。各两完整窗口，不扫参数，不改生产。基准固定753/646sessions、36/31次monthly choice，fee0/slip5。每一分支独立现金和持仓，月度selector按该分支当时账户重新选股；只有arguments全量exact才可复用既有选择。最多134新增搜索（2候选×67月，每次8192预算），不承诺都在06:00前完成，截止保存前缀不能称完整成绩。

## A状态机

在真实risk.apply之后、生成订单之后处理BUY；已有SELL全部原样，包括20%退出。以SID+当前month decision绑定一轮补仓episode。首次正缺口Q冻结，仅首笔订单floor(Q/2)；用kernel提供state.order_log中本episode订单id的真实ASSUMED_NEXT_OPEN_FILLED数量确认成交，不能看目标变化或估计成交。首次完全未成交保持阶段1，不每日对新缺口递归减半；若初始Q=1首阶段数量0，明确记录按计划跳过第一开盘，下一开盘进入阶段2。任何实际部分成交后下一开盘转阶段2，按最新风险有效目标减实际持股，真实现金配给，不再half。达目标/原risk退出/新月目标更换结束episode。公司行动数量转换必须在kernel原机制执行，跨SID尚未完整支持的episode应失败而非静默丢弃。

## B因果归因及状态机

不能将所有held>monthly_ceiling的SELL都算cap。月度rerank选出赢家时，依据同次best_by_k及rerank_audit找到被裁剪前赢家篮子U；逐证券确认min(U,floor(equity/(2*decision_price)))等于实际选中cap篮子C，记录来源与哈希。strict-improvement=false时使用原raw赢家；true时使用审计source cardinality，不能误拿raw原赢家。

对仍在当月有效目标且未20%退出的证券，持股h，原总卖出max(0,h-C)：非cap必要卖出max(0,h-U)首开盘全部执行；纯cap增量=max(0,min(h,U)-C)，首开盘执行ceil(纯增量/2)，次开盘按真实剩余完成。risk effective为0、证券被新目标移除、终止身份或未获后行动mark时不应用此缓冲，遵守原退出/等待。首次未成交不能算完成。必须冻结episode，不能每次half剩余。临时持仓可超过cap，单列超额股数/名义价值/持续sessions，不能说风险约束完全不变。

## 真实接口与尚需实现

`backtest/historical_dividend_frontier_research.py` 已有真实月度账户选择、risk、企业行动、分红全链；其risk target强制<=ceiling，所以不要把缓冲目标塞进risk adapter。应在独立新wrapper的订单形成后、交原kernel前应用执行分批，单列original risk target与execution-stage target，不伪造原risk。原kernel `historical_dividend_next_open_book_research.py:187-192` provider state有完整order_log供确认成交。原kernel保持sell-first实际成交后现金可供BUY的研究假设；分批卖出会改变当日现金及以后选择，不能用基准未来target。买方不得使用未成交卖款。

独立复核必须理解执行分批状态并重新算订单，旧review若强制差额订单全量需新增隔离dispatch，不可跳过verify_risk/selection。公司行动包含旧窗SMCI跨SID拆分/清仓及股息；新分支可能暴露原基准未暴露事件，原exposure gate仍必需，不能因为baseline完整就宣称所有分支可执行。两窗训练/OHLC及公司行动复用已审execution_inputs，不新拉数据。

## 首轮动作清点

`tmp/two_stage_bull_bear_20261029/trigger_inventory.json`：两窗原BUY建议158/33条（包含未成交重复，非成交数）；B粗必要条件8/12条，不代表已证明纯cap增量。现阶段不读取候选收益，不为强造差异改规则。需先完成归因与小fixture：Q1、部分成交、无现金、第二次不half、risk退出优先、split调整、跨月独立重选。来源/权益不能承接则明确停止前缀，06:00不再启动新工作。
