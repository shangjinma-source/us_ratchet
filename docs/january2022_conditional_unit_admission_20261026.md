# 2022 年 1 月：单位准入缩至 11 项明确复核

## 后续已完成：101 个真实成员的训练编译通过

新增的三项官方拆股完成证据和八项 SEC 2021-12-31 名义价锚已实际接入。现在 **101/101 均为 `READY_CONDITIONAL`，100 个发行人、253 个训练收盘、12 个场景全部由真实 compiler 成功产生**，`compiler_rejection=null`，没有运行选股搜索。早先 90/11 的进度记录保留如下，不代表当前状态。

三项官方完成证据逐一与 provider 日期和比例核对，证据包所列文件 hash 已重算验证。八个新成员采用 SEC 同日持仓市值除股数、显式四舍五入至报价美分的决策成本；逐份 provider 原响应 hash 与锚点审核记录匹配。LCID 等缺少未来事件说明的个案，成本直接来自真实决策日锚，不靠猜未来拆股；`decision_cost / provider_decision_close` 仅定义本研究月价格坐标常数，不作为未来股票行动事实。

`january2022_training_diagnostic.json` 同时包含 compiler 的完整真实 `window`、`admission`、源 hash、101 身份映射、逐证券单位依据，以及返回的 `compiled_search_arguments`，不是只有“准备好”状态。脚本支持直接 CLI：

```powershell
D:\python\python.exe scripts/prepare_january2022_training_diagnostic.py
```

**这里只完成训练准入与编译。** 2022 年 1 月执行报价尚须用各自固定坐标还原，并在组装时与 compiler 的 decision_cost 精确相等；月内真实公司行动另核。`execution_admission=false`、`economic_run_completed=false`、`search_calls=0`，没有把训练成功称为策略牛熊回测完成。

## 先前进度留存

已将单月真实输入的 **90/101 证券** 写为 `READY_CONDITIONAL`，填入有证据的名义 `decision_cost`，不再将全部第三方行情无限拒绝。全窗口仍拒绝编译，因为剩余 11 只未完成，未删除它们，也未跑搜索。

采用明确的研究条件口径：证券身份已绑定；253 个 provider close 完整；2020-12-31 SEC 每股名义锚经已存事件乘积复原后差不超过 0.02 美元；训练窗内公司行动须已有语义核对。窗口后的因子在 12 个 close 比值中严格抵消，保留训练 close 原坐标，只对 2021-12-31 的 decision_cost 乘回该日之后的统一因子。此为条件输入，不宣称完整 point-in-time 或投资表现认证。

例如 NVDA 的 2021-07-20 拆股已获官方确认；其训练数据保持连续拆股坐标，决策成本只乘 2024 后 10 倍因子，不再乘已经发生的 4 倍。EXC 的 2022-02-02 分拆因子位于训练和 2022 年 1 月执行之后，在本单月只作为价格坐标复原 1.402，不在 2021 年账中创造子股或增加母股数量。后续覆盖 2 月时，分拆动作仍必须真实处理。

剩余 11 项不是泛泛“单位未知”：

- **CSX、ISRG、MCHP**：分别有 2021-06-29 3:1、2021-10-05 3:1、2021-10-13 2:1 的窗口内 provider 事件，需确认普通拆股语义；窗口后常数抵消的理由不能替代它们。
- **ABNB、CRWD、DDOG、FTNT、HON、LCID、PANW、ZS**：首次2020锚点不包含这8个新成员，需补单点名义价锚或有界坐标核查。已有具体反证说明不能默认因子1：缓存 CRWD 有2026年4:1；PANW还有2024年2:1，原2023截断响应只显示2022年3:1；HON有2025/2026分拆类非整数因子。FTNT有2022年5:1。ABNB/DDOG无缓存拆股事件仅是现有信息，LCID/ZS在该缓存目录无文件，不能把缺文件解释为无行动。

真实产物 `tmp/qqq_20201231_anchor_20261025/january2022_training_diagnostic.json` 含每证券源hash、锚误差、截止后因子、窗内待核动作、90条conditional成本及11条明确拒绝。编译器仍实际返回 `WINDOW_NOT_ADMITTED`，因为全成员窗准入尚未成立。已验证常数抵消的精确分数等式、90/11计数、NVDA/EXC已填成本及ISRG仍拒绝。仅修改独立研究准备脚本，未修改共享矩阵、生产或策略。
