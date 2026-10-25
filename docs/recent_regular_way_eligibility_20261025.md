# CEG / GEHC：253 日历史资格已明确

沿用当前编译器的 `INSUFFICIENT_253_SESSION_PREDECISION_HISTORY` 规则，保留完整成员，只排除当月新买入训练候选；不将 when-issued 临时代码的历史拼入 regular-way 训练。没有变更策略、经济回测或生产配置。

CEG regular-way 从 **2022-02-02** 起，1/19 开始的是 CEGVV when-issued，已由[现有分拆证据](exc_ceg_distribution_evidence_20261025.md)核实。按已有共同会话日历，到 **2023-01-31 仅 250 日**，所以 **2023 年 2 月交易目标仍不应纳入 CEG 新买入候选**。此前供应商首报价计数误把 when-issued 算进历史，这次补正。253 日达到日为 2023-02-03，首次合格月末为 2023-02-28（对应 3 月交易）；历史长度合格仍不是价格身份/单位全面准入。

GEHC 的[发行人完成分拆公告](https://investor.gehealthcare.com/news-releases/news-release-details/ge-healthcare-completes-spin-and-begins-trading-nasdaq)在 2023-01-04 明确当天开盘开始独立交易；[Nasdaq 交易通知](https://classic.nasdaqtrader.com/TraderNews.aspx?id=eca2022-405)将此前 GEHCV when-issued 与 1/4 regular-way 分开。以 **2023-01-04** 起算，到 2023-12-29 仅 249 日。因此加入指数后的所有 2023 年月末都不足 253 日，不需要继续等待缺失历史下载，也不能拿 when-issued 凑数。

| 证券 | 不足 253 日的实际决策日范围 | 对应实际交易月 | 首个历史长度合格月末 |
|---|---|---|---|
| CEG | 2022-02-28 至 2023-01-31，共 12 次 | 2022-03 至 2023-02 | 2023-02-28 |
| GEHC | 2023-06-30 至 2023-11-30，共 6 次 | 2023-07 至 2023-12 | 当前研究期内没有 |

另保留 GEHC 2023-12-29 终端边界不足记录，但不将 2024 年新增为交易评估月。合计解决 **18 个实际决策窗口**（原 17 个加补正的 CEG 2023-01-31）。V3 其余左边界不足多为数据源截短，不由这两项证据泛化成上市不足。

每次判断均保存公布日、regular-way 日期、计数、全体合法训练日期、规则理由和官方来源；公布日早于所涉月末，资格不受事前可知性阻塞。分拆所得持仓仍要计估值/收益/回撤，训练不入选不能当作忽略分拆权益的理由。

复现：

```powershell
D:\python\python.exe scripts/review_recent_regular_way_eligibility.py
```

输出 `tmp/qqq_20201231_anchor_20261025/regular_way_eligibility_v1.json`，留待下一轮覆盖矩阵统一接入，不覆盖 V3。参考会话是三只已存美股时间戳一致结果，非官方交易日历认证。GEHC 事实记录来自网页核读，不冒充原始 HTTP 归档。
