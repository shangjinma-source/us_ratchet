# 历史普通股息接入合同

## 当前边界

`frontier_capped_next_open_research.py` 调用 `current_quantity_v2_next_open_book.run_next_open_book`。后者222—286行公司行动分支没有普通股息；未知持仓事件会阻塞。旧版声明普通股息排除。此次新增独立模块 `backtest/historical_dividend_ledger_research.py`，未修改冻结引擎、策略、生产账户，**未完成主账整合**。

已检查 `paper_dividend_journal_v1` 与 `data/paper_dividend_payment_v1`：它们依赖真实纸面账户的来源准入、支付审核与重放，明确不影响可用现金。本模块复用其分离权益和支付、幂等的原则；不伪造这些审核对象来调用现有接口。`conditional_gross_income_schedule` 仅为非再投资覆盖层，不能直接当作交易现金。

## 事件与时序

事件必须明确 `event_id/security_id/ex_date/payment_date/amount_per_share/withholding_rate/assumption/currency`。金额使用 Fraction；税率为显式研究假设，并不代表用户实际税务。支付日允许 null，不能从 WIKI ex-dividend 推导。当前研究版本不处理费用、支付修订、特殊除息/due-bill、负调整或实际券商到账。

1. 除息日交易前，以前一交易日结束持仓（明确 opening_quantity 接口）生成净应收。
2. 应收进入权益，但不进入可用现金。除息日卖出不失去应收；当天新买入没有对应权利。
3. 已知支付日到达后，可按明确研究时序支付，增加现金并等额冲回应收；非交易日支付在下一观察点反映，现金可用于哪个订单阶段必须由未来主账调用顺序明确。
4. 未知支付日永久保持应收，直到取得新证据并设计受审计的修订机制；本版本不会伪造或自行推迟支付日。
5. event_id 重试同输入返回原结果，不同输入拒绝；payment_id 重试同输入幂等；同权益换另一个支付ID仍拒绝重复支付。

## 下一轮主账接入要求

- 版本化引擎明确除息前取权、交易和支付先后；同日拆股/分红先核实每股单位，特殊派息另行处理。
- 将 receivable 加入权益而排除 sizing；仅把 paid_cash 的增量记入现金，不要每次重复加累计值。
- 使用原始价格时需检查普通股息全覆盖；使用含股息复权价不得再重复计息。
- 旧基线与新方案同时接入同一账法再比较，不能只给候选方案加股息。
- 当前模块仅验证会计状态转换，没有证明数据完整、真实支付、完整收益或策略优越。

验证命令：`D:\python\python.exe -m unittest discover -s tests -p test_historical_dividend_ledger_research.py`。覆盖期初持仓权利、除息日零持仓买入、事件冲突、提前支付拒绝、重复支付、支付权益守恒与未知支付日。
