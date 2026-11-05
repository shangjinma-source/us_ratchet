# 固定动量名单行动库存复用（执行前设计）

仅读设计，等待67月确定名单；没有经济回测、没有账户写入。目标是找新策略可能暴露的事件，不以V27原持仓或原通过记录代替新范围。

## 最小接线

新建一个独立库存脚本即可，不启动runner。输入为新名单文件/hash；36/31月必须完整且与已冻结session_dates对齐。每月使用门控后目标SID（门控关闭为空），不是仅排名前10。保存排名集合、实际门控目标与两者差异，便于审阅。

- 上月目标集合每SID给1股作为范围标记，本月目标集合每SID给1股；首月旧仓为空。并集构成本月潜在暴露。1股仅表示非零暴露，不表达20k可负担、真实数量、分红金额或风险峰值。
- 继续持有或新目标查 `(decision_date,next_decision_date]`；上月有、本月无的卖出股票仍查到active next-open（含当天）。末月截止窗口末日。
- 这是假定月目标可正常执行的保守潜在范围，20%退出可能使真实暴露更短；不能把库存失败当成实际发生，也不能把库存通过当成订单成交保证。无法卖出/现金不足/跨身份等仍由经济执行器逐次gate，不沿用虚拟持仓。
- 原始事件库存和缺失来源完整保存，然后调用原gate；每项保存阻断/已映射、对应review/execution event及原来源hash。按SID/日期/事件类型汇总缺口，不按月份重复补同一笔。

## 复用的真实入口

早窗：`scripts/run_recent_continuous_probe.py::exposed_action_blockers`。后窗：`scripts/assemble_old_continuous_inputs_v1.py::exposure_gate`，再用 `scripts/run_old_continuous_probe_v4.py::admit_reviewed_dividends`、`admit_period_absence`。同原runner `scripts/research/run_downside_account_candidate_20261105_v3.py` 的装配顺序：

1. 基础 `tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json` / `tmp/old_continuous_baseline_20261026_v9/execution_inputs.json`。
2. 对应 `tmp/trend_2021_2023_20261026_v1/execution_inputs.json` / `tmp/trend_2024_2026_20261026_v1/execution_inputs.json` 中action_review，并校验原基准input相等及prices SHA。
3. `tmp/equal_four_20261105/source_review/admitted_supplement.json`：按窗口成对加入review_rows与dividend_events。
4. `docs/candidates/downside_bounded_execution_supplement_20261105.py::extend_execution_evidence`：已pin的9股息和ALXN/SGEN严格无行动子区间；不得扩大日期。
5. 后窗从 `research_contracts/downside_max10_resume_v9_20261105/freeze.json` 的 `additional_execution_artifacts` 读取九项（META/CEG/AZN/CTSH/LRCX/INSM/GOOG-KDP/ASML/GEHC），用 `docs/candidates/downside_absence_artifact_20261105.py::append_execution_artifact`。它分流无行动证明和普通股息成对加入，不能用review-only绕过执行账。

先验证freeze所有pins及每artifact内部pins、无冲突/无重复，再制作deepcopy，原文件不修改。不能把后窗artifact硬加早窗，或直接拿后窗已生成gate结果给新名单。

## 时序与边界

原gate包含active日卖出前已持有的除息权利；新买入active日普通股息只能在原gate明确零opening holding时作为零权益，不可删事件。拆股同日先调单位后成交的约束仍保留；1股库存不调用`admit_split_liquidation`来模拟可执行，因为该函数需要真实旧仓整数比例、目标归零和新月执行等条件。split/identity/ADS/混合并购均标记需实际账户数量复核，尤其SMCI持续目标、AZN转换、ALXN混合并购。未知行动不得用“本月卖出”跳过active当天。

后窗legacy缺流证明如需复用，必须按原精确证券、来源片段、完整session和hash执行已有legacy admit；没有证明时保留缺口。ASML最终分红计量的后验限制沿用，不能解释成当时已知信号。

输出仅 `ACTION_SCOPE_INVENTORY_NOT_ECONOMIC_ADMISSION`：67月输入集合与期间、每月原始/剩余事件、按证券事件唯一缺口及来源pins；不输出收益、不声称全部可交易。名单尚未收到，因此当前无覆盖率结论。
