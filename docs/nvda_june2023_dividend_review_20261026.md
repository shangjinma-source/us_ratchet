# NVDA 2023年6月普通现金股息

发行人2023-05-24财报公告实际HTTP200已保存：每股名义税前0.04美元，登记日6/8，支付日6/30。除息日6/7来自冻结Yahoo原事件1686144600，明确不是公告直接写明除息日。原供应商0.004不可直接入账，官方0.04也不能再乘价格恢复因子。

新合并审核：`tmp/nvda_june2023_dividend_review_20261026/combined_review.json`，保留全部ALXN/NVDA2021/SGEN旧行；来源含原NVDA行情哈希及官方原HTML哈希。官方HTML SHA256 `236c707a4aad00244e8064818fee37686b077e9b263578c976bb0ef4f3ffd825`。

6/1实际成交并在6/7期初仍持有的股份享权。若届时10股仍在，应收税前0.40美元；必须读取重放实际数量，不能用目标数量代替，更不能使用除息日首次买入零权益豁免。6/7计应收、6/30前不能用于买入；付款日遵循已声明引擎时序。税前gross研究由主线程显式声明，不推断用户实际预扣税。

来源：https://investor.nvidia.com/news/press-release-details/2023/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2024/

首次资料整备未运行回测、未更改生产。后续 v6 连续账本真实计提 10 股共 0.40 美元，6 月 30 日支付一次，现金及下一月选择衔接已独立复核：`tmp/recent_continuous_baseline_20261026_v6/june_dividend_cash_audit.json`。

## 后续两个季度资料

同样保存了发行人 2023-08-23 和 2023-11-21 财报原文。每股均为名义税前 0.04 美元；登记日分别为 9/7、12/6，支付日为 9/28、12/28；冻结 provider 的除息日分别为 9/6、12/5。新文件 `tmp/nvda_late2023_dividend_candidates_20261026/combined_review.json` 保留全部旧记录，未覆盖六月证据。是否产生权益仍以实际除息日期初持股为准，不因资料存在就假设持有。
