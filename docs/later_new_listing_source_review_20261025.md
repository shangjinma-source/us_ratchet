# 后窗新上市股票来源复核

2026-10-25，限定检查后窗现有输入中的 SNDK、CRWV、ALAB、ARM、NBIS。没有运行新优化或收益回测，没有改变投资域、历史输入或生产目标。

结论：这五只股票实际使用的 18 个股票月份中，未发现上市前训练、旧股票代码历史误拼，或未披露的母股价格代理。4,554 个训练收盘和 216 个实际搜索情景，均逐项等于来源 SHA 已绑定的同代码整段行情。SNDK 的 63 日执行 OHLC、63 个组装后收盘和 4 笔基线成交价，也与同一来源及已登记的 10 bp 滑点一致。

| 股票 | 后窗实际入域月数 | 首个决策日 | 最早使用训练日 | 官方交易边界 |
| --- | ---: | --- | --- | --- |
| SNDK | 3 | 2026-04-30 | 2025-04-29 | 2025-02-24，分拆后普通交易 |
| CRWV | 1 | 2026-06-30 | 2025-06-27 | 2025-03-28，IPO |
| ALAB | 1 | 2026-06-30 | 2025-06-27 | 2024-03-20，IPO |
| ARM | 12 | 2025-07-31 | 2024-07-29 | 2023-09-14，ADS 上市交易 |
| NBIS | 1 | 2026-06-30 | 2025-06-27 | 2024-10-21，恢复 Nasdaq 交易 |

每个实际窗口均为 253 个完整观察日，最后一日为该次决策日。日期有序、没有重复或未来日；决策价格、训练收盘和 12 段训练收益率使用相同来源。五只股票的原始行情均标记 USD/Nasdaq，训练口径均为 `ORDINARY_WHOLE_QUOTE`；没有走 HON、CMCSA、WDC 等已披露特殊坐标分支。ARM 的证券形式是 ADS，不能把它写成美国普通股股份。

SNDK 原始源从 2025-02-13 的 when-issued 期间开始，但现有三个窗口最早使用的是 2025-04-29，因此未用到那段数据。原始源没有拼接此前旧 SNDK 的历史。NBIS 原始源始于 2024-10-21，未拼接旧 YNDX 停牌前历史；ARM 源始于 2023 年新上市，未拼接早年的旧上市历史。上述结论只覆盖本次实际输入，不能代替以后重用早期数据时的资格守门。

这五只股票中，现有后窗基线只有 SNDK 成交：2026-05-01 买 21 股、6 月 1 日卖 4 股、7 月 1 日卖 3 股、7 月 6 日卖 14 股。它使用独立 SNDK 行情，没有把 WDC 的分拆配股比例乘入这段训练或执行价格。

## 一手日期依据

- SNDK：[公司向 SEC 提交的 8-K](https://www.sec.gov/Archives/edgar/data/2023554/000119312525033433/d849281d8k.htm)，说明分拆后普通交易日期。
- CRWV：[公司投资者 FAQ](https://investors.coreweave.com/additional-resources/investor-faqs/default.aspx)，说明 IPO 日期。
- ALAB：[公司 2024 年一季度业绩公告](https://www.asteralabs.com/news/astera-labs-announces-financial-results-for-the-first-quarter-of-fiscal-year-2024/)，说明股票开始交易日期。
- ARM：[公司 IPO 完成公告](https://newsroom.arm.com/news/arm-announces-closing-of-initial-public-offering)，说明 ADS 开始交易日期。
- NBIS：[Nasdaq 恢复交易公告](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-resumes-trading-nebius-group-nv)，说明原 Yandex 证券停牌及 NBIS 恢复交易日期。

这是在 2026-10-25 对一手材料的追溯核验，不证明历史决策日已经抓取到该材料，也不以季度名单的运行日期代替公开时间戳。

## 证据与边界

可复核脚本：`tmp/later_new_listing_scope_20261025_v1/audit.py`。逐项结果、输入与原始源 SHA：同目录 `report.json`。该脚本只读取已有文件，不导入优化器或账本执行器。

复核绑定了现有 `later_assembled.json`、`next12_training_prepare`、`next12_execution_prepare` 和 `capped_actual_reselection` 基线，同时读取既有身份审核、行情坐标说明和特殊模型政策。它证明本次数据传递一致，并排除了本次五只股票的已知交易起日错误。

它没有独立证明行情提供商每个历史价格真实无误，也没有证明公司行动完整性、全域历史成分完整性或历史时点可得性。后窗原有 `DATED_OFFICIAL_EVENT_CHAIN_CONDITIONAL`、`completeness=false`、非独立样本外等限制继续保留；早窗已确认的幸存者偏差和 FER/GEHC 资格问题也不会被本报告消除。本次没有因此升级策略证据等级或自动采用候选策略。
