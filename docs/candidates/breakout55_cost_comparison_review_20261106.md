# Fixed breakout cost comparison audit

CSX local reuse: only2023-05-30 and2025-08-29 individual releases in rsi2_official_history batch. No complete official CSX history or2024-02-28 payment evidence found in the bounded local source search. Do not extrapolate prior dates. Strategy agent informed.

## Current comparability
New breakout includes Trade25 brokerage; saved V27 books are zero commission plus5bp slippage. Thus V27 versus breakout is currently unequal costs and cannot be advertised as matched net-return comparison. More fees do not imply an exact final-equity decrease because reduced quantities can avoid future losses, so no monotonic performance shortcut is valid.

QQQ paid-reinvestment books were passed through the same core-based fee scenario analyzer: both windows have zero brokerage in both timing scenarios, with first threshold crossing waiver honored. Initial buy20kUSD is below250kHKD at7.8; early second small reinvestment also below monthly threshold; later no second whole share. QQQ includes5bp per buy and gross dividends, matching breakout cost convention subject to declared FX/tax/payment assumptions. Failure versus this QQQ does not require V27 fee replay to establish that particular failure.

## Executable V27 rerun path, not started
Entry is backtest/frontier_capped_next_open_research.py::run_frontier_capped_next_open with the ORIGINAL decision provider, same risk rules, monthly inputs, source/action gate, nominal prices and initial20k. Its book dependency is backtest/historical_dividend_next_open_book_research.py::run_next_open_book. Candidate qqq_risk_budget_account_runner.py shows an isolated namespace pattern but its altered selection rules must NOT substitute for V27.

The base book has sell and buy fills near lines343/355 with fee=q*fill*fee_rate. Fixed Trade25 fees cannot be expressed by fee_bps. Implement an isolated book copy or explicit injected fee planner only; use docs/candidates/trade25_execution_planner_20261106.py with each known next-open aware NewYork09:30 timestamp, complete HK-month turnover and fixed7.8 scenario. Sell proceeds net of fee must precede buys. Preserve original buy quantity pro-rata policy: the existing factor uses aggregate linear costs, so fixed-fee reservation must adapt that funding calculation without silently replacing V27 allocation by sequential greedy sizing. Each actually committed order updates turnover; rejected/unfilled orders do not. Preserve dividend/merger rights and settlement timing.

Initial rule/selection input metadata fee_bps0 denotes solver objective convention; explicitly disclose objective unchanged and execution uses actual Trade25. Do not set fee_bps18 or modify monthly risk/selection rules. Require zero-fee injected mode reproduce existing full book, then fee-affordability, HK reset, cross-threshold waiver, corporate-action cash conservation tests before full replay. Full replay must recompute later account-aware decisions under altered capital, not reuse fixed historic quantities or subtract fees from terminal equity.

No full V27 rerun, candidate mutation or production change performed by this review. Only undertake cost replay if new candidate otherwise merits comparison/deployment.
