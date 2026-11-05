# QQQ paid-cash integer reinvestment benchmark

Fixed before results: initial USD20000, no leverage/flows, whole shares, every session open invests available cash at open plus5bp; zero commission. Ex-date opening holdings accrue gross entitlement. Exchange payment date posts at first available session close; spendable only next session open. Unpaid rights enter total equity but never buying power. Terminal valuation at close without liquidation. Existing no-reinvestment benchmark remains unchanged.

Sources: reused pinned QQQ raw OHLC and provider event dates from existing qqq_fair_hold. Nasdaq exchange dividends endpoint returned HTTP200 with full payment history, saved `tmp/qqq_reinvest_20261106/nasdaq_dividends.json`. Exact Nasdaq amounts replace provider rounded amounts; every event date set matched, differences <=.001 verified and recorded. This amount precision change explains tiny difference even in late window with no additional whole share purchased. Issuer/exchange scheduled payment is not verified HSBC receipt; zero withholding is research convention.

Full early753/later646 sessions independently recalculated: early CAGR9.83338%, closeDD34.78257%, terminal26480.5092,2buy fills; late CAGR22.72064%, closeDD22.54312%, terminal33950.0404,1buy fill. Late dividend+residual cash never buys another whole share at eligible opens. Neither window stitched as continuous account.

Four counterexamples pass: same-day payment cannot fund open; cash below one share retained; unpaid dividend cannot fund buys; ex-date new shares not entitled. Report includes source hashes, event mapping, annual results and recovery metrics. Remaining data/universe/conditional-action limitations of RSI are independent of this benchmark and must remain explicit.
