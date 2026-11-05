# RSI2 回测：AMGN / AAPL 六项现金分红核查

目的仅为历史账户权益计算，不将后来发布的财报作为当时交易信号。

| 股票 | provider 除息日 | 原单位每股美元 | 发行人支付日 |
|---|---|---|---|
| AMGN | 2021-02-11 | 1.76 | 2021-03-08 |
| AMGN | 2023-02-14 | 2.13 | 2023-03-08 |
| AMGN | 2024-02-15 | 2.25 | 2024-03-07 |
| AAPL | 2021-05-07 | 0.22 | 2021-05-13 |
| AAPL | 2023-08-11 | 0.24 | 2023-08-17 |
| AAPL | 2024-11-08 | 0.25 | 2024-11-14 |

AMGN 采用公司主站三份季度结果原文，均 HTTP 200：

- https://www.amgen.com/newsroom/press-releases/2021/04/amgen-reports-first-quarter-2021-financial-results
- https://www.amgen.com/newsroom/press-releases/2023/04/amgen-reports-first-quarter-financial-results
- https://www.amgen.com/newsroom/press-releases/2024/05/amgen-reports-first-quarter-2024-financial-results

AAPL 采用 https://investor.apple.com/dividend-history/ 官方历史表，HTTP 200，表内明确 Regular Cash，金额不作拆股调整；所选事件均在 2020 年拆股以后。

发行人记录日与 provider 除息日分开保存，不能混用。逐项核对已保存 provider 原事件时间戳与金额，保留原文字节、SHA256、观察记录和精确有理数金额。AMGN 投资者站历史表使用第三方 Mergent 数据，此表仅作定位，不充当本次发行人原始证明。

本地证据：`tmp/rsi2_amgn_official_20261106/review_rows.json`、`tmp/rsi2_aapl_official_20261106/review_rows.json` 及同目录原文。已经交策略任务独立审查接入；不代表完整牛熊回测完成。

限制：税前历史会计口径，未证明券商实际入账时刻或账户适用预扣税。不得将其作为税后真实账户收益或无其他公司行动的证明。
