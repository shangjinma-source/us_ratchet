# 风险预算候选：现存数据预检

结论：**63日日频价格与同日QQQ覆盖已有；经过点时公司行动处理的完整日含息收益序列尚未就绪。** 不能直接把现有12个训练情景或名义执行价格喂进波动计算。本轮只读、无网络、无经济回测；等待B完整结果，候选仍沿原V27，不夹带B规则。

## 已实际检查的数据

| 窗口 | 已有文件 | 检查 |
|---|---|---|
|2021—2023，36个决策月|`tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json`，`windows[].window.training_dates/candidates[].training_close`|有保存的253日价格；现存非空training_close长度均253；每窗末64个日期与QQQ无缺失|
|2024—2026/7，31个决策月|`tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json`，`windows[].training_dates/candidates[].training_close`|同上，末64个日期QQQ无缺失；部分候选按原历史不足规则排除，不得因波动数据缺失另行改池|
|QQQ|`tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin`及`data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin`|合并1704个有收盘价日期，2020-01-02至2026-10-13；上述67个决策月末64日覆盖均完整|

63个日收益需要64个收盘价。检查只验证现有日期和数组长度，未把所有价格升级为独立来源认证，也未计算策略收益。

`backtest/return_priority_monthly_training_inputs.py::compile_monthly_training_window` 确实先读取253日training_close，再输出12个互不重叠21日价格情景；原始日数据没有丢失，只有编译后的training_scenarios不够计算日波动。

## 可复用和缺口

- `scripts/prepare_recent_training_windows.py::prepare/reviewed_coordinate_event` 保存了早窗价格坐标与拆股处理。其明确是价格信号；EXC等保留供应商分拆调整，不能称为实际母子资产含息总回报。
- `scripts/compile_old_windows_raw_signal_v2.py` 及保存v4窗口明确多数为 `FIXED_SOURCE_RAW_PRICE_SIGNAL_NOT_TOTAL_RETURN`，部分为供应商分拆调整信号。后窗逐候选月记录中3067条为前者、60条为后者，另外2条为条件拆股调整、3条未标此字段。固定未来比例在同一段纯比值中可以抵消，但并不认证复杂公司行动或公告首次可见时间。
- `backtest/annual_simple_split_coordinates.py::training_close` 可将名义价格按截至decision_date已生效的**已审简单拆股**统一单位；`nominal_row`恢复历史名义坐标。它显式拒绝复杂公司行动，不能拿通用拆股替代ADS转换、分拆或现金并购。
- 两窗 `execution_inputs.json` 的 `assembled.actions/distribution_events/supported_conversions` 与 `dividend_events` 可复用事件结构；`backtest/historical_dividend_next_open_book_research.py::run_next_open_book` 已实现股息应收及付款。它们主要针对实际执行暴露准入，**不能自动覆盖每次新选股票此前63日内全部行动**。例如当前四股研究仍需补新暴露事件，说明有行情不等于有完整行动认证。
- `scripts/research/qqq_fair_hold_20261105.py` 可复用QQQ原始股息解析；无拆股。QQQ经济权益可在除息日计应收，不要求把未知付款日假装现金到账。构造风险信号时，股票也必须使用同一股息口径，不能一边含息、一边裸价格。
- 这些是现今抓取的回溯数据，并非当时接收归档；事件生效日筛选不等于已验证所有原文当时可得。研究仍应标条件性，不称完整PIT/OOS。

## 最小准备边界

若B结果后仍决定执行此候选，先对**原V27月度目标涉及股票**的每个末64日窗口，盘点简单拆股、股息和复杂分拆映射，生成独立于交易账本的同口径日收益输入及hash。日期不完整、复杂权益未定价或单位不明则明确阻塞，不零填、不用全样本复权便利替代、不另调观察天数。

不需要重新下载全市场日线，但目前还不能承诺零准备即可运行。若所需行动覆盖扩张成大工程，应停止该候选准备，不能借此再开无界补证。

## 经济判断

早窗V27年化负、回撤高，缩仓只有在高波动与后续损失关系足够稳定时才可能改善风险调整表现。若其选股期望收益本身弱于QQQ，现金缩放不会建立新的选股优势；还可能卖在下跌后并错过反弹。没有事后挑时点、没有计算“最优缩仓上界”，也没有理由预先承诺双优。只够作为一次有限机制备选，不能代替完整A/B结果判断。
