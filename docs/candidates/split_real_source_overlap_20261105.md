# SNDK / MRNA 真实本地重叠核验

本轮只读两只证券既有文件，未外部采集、未生成授权或账户事件、未运行策略。实际脚本 `tmp/native_real_overlap_20261105/check.py` 已一次完成，细证 `tmp/native_real_overlap_20261105/result.json` 保留逐日 Fraction 值、差额、文件路径与 SHA256。

|证券|manifest 对实际训练源|训练与当前单位基线 capture 的共同已闭市会话|差异|
|---|---|---|---|
|MRNA|253 / 253 精确相等|2026-10-09 至 2026-10-30，共 16 日|0|
|SNDK|253 / 253 精确相等|2026-10-09 至 2026-10-30，共 16 日|0|

训练 manifest 为 `tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json`，实际训练源分别为其引用的 `tmp/monthly_recovery_20261103/normalized_v2/{MRNA,SNDK}/{ticker}.response.bin`。实际源 SHA 与 manifest 原有 source_hashes 一致。每个训练日期与 raw close 数组逐项比较，没有缺失或价差。

单位基线使用当前目标明确绑定的 `data/strategy_account/evidence/700ee09002d64c6f87fc7e9b1d657ebd/unit_review.json` 下两证券引用的 receipt/raw（具体文件在前份 readiness 报告及细证）。receipt 文件名 SHA、raw_sha256 均核对通过。比较字段只使用 chart.indicators.quote[0].close，不使用 adjclose。JSON 小数直接解析为精确十进制字符串，再转 Fraction；没有浮点容差，也没有乘除人为拆股系数。

闭市判定采用活动引用 `research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json` 的实际 close 时间，要求不晚于每份 receipt.started_at。两份 11/3 盘中 capture 均包含尚未收盘的 11/3 日线，已排除；11/2 已闭市，但晚于 manifest 的 10/30 截止，因此不是共同会话。没有把这两个日期伪造为重叠相等。

结论只限：当前 manifest、其训练原字节和单位基线捕获在所列共同区间中价格坐标连续，未发现具体日期字段不一致。两代材料均来自同一供应商，精确相等不是独立双源认证，不能据此认定价格为未复权名义价、含息价或已明确授权的 split-adjusted 价。raw 未返回股息/拆股也不证明未来无行动。仍须保留原条件性口径，不能据此签发 NativeCaptureReview grant 或激活未来拆股。

## 供应商说明的补充核查

根线程于11月5日检索到Yahoo自身[MRNA历史页面](https://ca.finance.yahoo.com/quote/MRNA/history/)的字段说明：Close为拆股调整价格；[Yahoo adjusted close帮助](https://help.yahoo.com/kb/SLN28256.html)说明Adjusted Close还包含适用的股息调整。前者检索快照约两个月前，后者检索当日；直接打开帮助及SNDK历史页均遇429，未取得可归档的完整响应，不能把搜索摘要当作执行来源收据。

这缩小了下一步问题：不是继续寻找是否存在一般性字段说明，而是确认实际chart接口quote.close与所述字段的一致性、具体响应的单位截止时点和真实公司行动。不能把split-adjusted误标AS_TRADED，也不能据帮助页证明每个API响应无错误。本轮不更改任何授权、生产字段或事件。
