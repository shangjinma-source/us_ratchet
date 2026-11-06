# 整股账户适配与连续QQQ独立复核

## Adapter修复复验

`tests/test_roa_daily_account_independent_20261106.py` 实际unittest 5/5通过。先前实际负open成交与混合merger丢股票腿问题均已修：实际持有/拟交易价前置正值校验并拒bool；现金merger含股票对价字段受控拒绝，不静默只入现金。

独立反例覆盖：除息日新买不取得既有分红、除息日卖出保留旧持股权利、支付日收盘才入现金；现金并购未到账计应收/NAV不购买力、D1收盘支付保持总权益；非法价和混合对价拒绝。此为模块正确性，不表示完整经济账户回测完成或获利证明。

命令：`D:/python/python.exe -m unittest discover -s tests -p test_roa_daily_account_independent_20261106.py -v`。

## 连续QQQ基准

源码 `scripts/research/qqq_continuous_paid_reinvestment_20261106.py` 与复用run_book已读；结果 `tmp/qqq_continuous_paid_reinvestment_20261106.json` source pins全部匹配。独立读取原始OHLC与已pin分红，逐日用Fraction重建现金/整股数/应收/NAV，并比对所有实际orders；1399会话、23除息事件、3次整股买入全部一致。事件集合直接与原provider完整集合核对，不仅继承两窗报告，金额差不超过原明示.001舍入范围。

2020-12-31锚点至2026-07-30：独算年化15.5249134%，每日收盘最大回撤34.7825665%，期末44,727.2538075美元。初始20k，首会话open买入；除息前持股份额确认，发行人支付日（非交易日延至下一会话）收盘记现金，随后会话open整股再投，未到账应收持续入NAV。没有额外入金、无终点卖出费用。

适合作为正式账户候选的统一整股、gross分红、0佣金、5bp买入滑点参考。不是HSBC税后真实到账，不能用它与仅价格候选直接声称税费后双优；候选需同样股息/税率/到账与成本假设。独立摘要 `tmp/qqq_continuous_independent_20261106.json`。
