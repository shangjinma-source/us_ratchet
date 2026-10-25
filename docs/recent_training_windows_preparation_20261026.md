# 全 36 月真实训练输入已编译

`scripts/prepare_recent_training_windows.py` 消费冻结的 124 证券 fixed_source_plan，逐份核对来源哈希，未改旧单月 probe。产物 `tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json` 的 36 个窗口均实际通过 compiler，决策日期从 2020-12-31 到 2023-11-30，对应 2021—2023 执行月。18 次合法短史排除保留完整成员；没有收益搜索或经济账本运行。

## 特殊训练口径

训练保持既有 V27 的 provider close 价格信号，未改为现金分配总回报策略。未来统一常数在训练比值中抵消；decision_cost 单独恢复名义单位。价格因子不能直接当执行股数事件。

EXC 2022-02-02：保留 provider 分拆复权 close 为价格信号代理。1.402 仅用于事件前名义价格坐标，母股数量不变；官方权益为每 3 股 EXC 得 1 股 CEG。此信号不是逐日 EXC 加 CEG 权益的精确总回报。执行账本仍须独立创建、估值及交付权益，不能把训练调整作为股数拆分。来源 `docs/exc_ceg_distribution_evidence_20261025.md` 与 `tmp/exc_ceg_distribution_20261025/web_parsed_evidence.json` 已固定哈希。

MTCH 2020-07-01：旧股到新股基本比例 1:1，另有 3 美元现金或可选额外股数；旧/新 CUSIP 为 57665R106 / 57667L107。独立旧行情 134 日中 133 日完全吻合，原 close 没有被 3.502 回调。保留原 provider 事件供审计，但 apply_nominal_scale=false，禁止乘回该因子。训练明确采用旧/新 MTCH 价格身份桥，不计额外现金/可选股数，不能称总回报；2021 执行也不虚构 2020 持仓补偿。`tmp/mtch_reorganization_20261026/evidence.json` 及全部引用来源校验哈希。不同日期、证券或因子的复杂事件仍拒绝。

CEG/ON/TTD 官方 QQQ 名义锚分别 86.21（2022-12-30）、83.53、71.96（2023-12-29），与固定源误差均小于 0.000002。按明确美分精度校准价格单位，不改变历史成员、资格或训练比值。来源 `tmp/ceg_on_ttd_anchor_20261026/three_anchor_review.json` 保留日期、官方表和固定行情哈希。

## 复现与边界

```powershell
D:\python\python.exe scripts/prepare_recent_training_windows.py
D:\python\python.exe -m unittest discover -s tests -p test_recent_training_coordinate_policy.py
```

三项必要测试验证 MTCH 因子排除、特殊事件例外不能泛化、EXC 仅价格单位而非股数。下一步仍是 36 月执行输入及真实公司行动/现金分配衔接；训练编译通过不等于策略年化或回撤目标完成。
