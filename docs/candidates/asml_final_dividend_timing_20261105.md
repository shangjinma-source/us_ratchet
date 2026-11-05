# ASML最终美元股息：除息与公布时点审核

仅静态读取现行冻结实现，未运行选股或经济回测。待补证的4月Final于4/28公布、4/27除息，7月Final于7/28公布；最终金额及日期以news独审artifact为准，不在此文件另行认证。

本次核对代码行：`historical_dividend_next_open_book_research.py:170`独立应收，`:187`传provider状态，`:411`付款入cash，`:420`报表股息应收；`continuous_guided_cost_monthly_provider.py:156`可配置财富及`:161`选股状态；`qqq_risk_budget_account_runner.py:82`价格风险输入。行号对应当前冻结字节。

## 当前决策是否读取提前确认的美元应收

- `backtest/historical_dividend_next_open_book_research.py` 将股息记在独立 dividend_state，除息前持仓获得应收；传入order_provider的state.receivable是原非股息权益变量，不含该股息应收。最终金额加入daily_ledger.equity，但付款日收盘前不进入cash。
- `backtest/continuous_guided_cost_monthly_provider.py` 的月度配置财富仅为cash加已持股数乘当日close；新选择account_state只含cash/shares/reserved_cash，不读daily_ledger的总权益。普通股息应收不进入仓位预算。
- `docs/candidates/qqq_risk_budget_account_runner.py` 当前实际仅用原MonthlyExit，risk.apply输入close、target、单位及已核调整；`core/monthly_peak_exit.py` 不读美元应收或账户净值。
- v3续接读取daily_ledger仅作已完成前缀完全相等校验，不用于择股/限仓/风险信号。除息前的gate只检查事件会计可重放性，不将股息金额作为候选打分。

因此在当前固定代码中，除息日按事后Final美元金额重述应收，不会改变Final公布之前的任何买卖决定、配置股数或20%价格退出。到实际支付日收盘入cash时该Final已发布。7月支付在8/5、晚于当前7/30截止时，仍只能保留应收。

## 可接受口径及不可作出的声明

可沿原回溯经济会计口径，用最终确定的税前美元权利确认除息收益，但除息日至Final公布前的权益及回撤是**事后最终金额重述**，不是当时可知的美元净值，不能称全PIT。该差额可能改变报告的日净值/最大回撤，不可以“决策不受影响”声称所有指标无前视估值问题。正式结果应显式标注，并在ASML实际有权股数非零时给出该段影响规模。

若要求严格当时已知净值，最小正确经济处理是先记已宣告EUR权利或未知USD应收，再在可靠可知时点确认美元估值；现有账本没有双币种/未知估值实现。不能将Final金额冒称提前已知，也不能为避开问题把除息日移到公布日或提前记现金。此分支不改冻结核心，不新增估值框架；由根确认使用条件性回溯口径后再接证据。
