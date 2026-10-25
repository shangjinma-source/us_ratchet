# 牛熊接入工程审计

2026-10-25，独立只读源码审计。用户未指定年份；2018—2023仅是之前自行提出的数据探测范围，不是验收约束。研究不依赖开盘，现有两窗不能作为完整牛熊证明。

## 已有可复用接口与真实缺口

| 文件 / 接口 | 实际能力 | 缺口与下一步 |
|---|---|---|
| `backtest/return_priority_monthly_training_inputs.py::compile_monthly_training_window` | 接受外部窗口、source_hashes、admission；要求253会话、完整成员分母、证券ID、12段21日收益；不能以行情缺失排除成员 | 这是结构编译器，不认证成员真实性、身份或价格单位；需要来源适配与独立准入，不能把社区CSV直接标成REVIEWED_CONDITIONAL |
| `backtest/return_priority_monthly_execution_inputs_v4.py::assemble_monthly_execution_inputs_v4` | 接受外部prepared；支持按日期分段的行情来源、分拆及部分证券转换；调用基础assembler | 可以复用任意显式日期范围，但必须补齐事件和合法单位；未知转换会带阻断标志，不能过滤掉 |
| `scripts/return_priority_current_monthly_actual_equity_inputs.py::prepare` | 旧实验行情恢复、输入拼装 | TRAINING/HOLDING/CALENDAR固定本地文件；强制12个窗口、250会话、2024-07-31至2025-07-30，**不是通用长历史接入口** |
| `scripts/run_drift_cap_comparison.py::WINDOWS/load_window` | 重放两组保存基准并核验来源 | 日期、月份数、基准路径固定；新实验不能覆盖此脚本或修改旧冻结证据 |
| `backtest/frontier_capped_next_open_research.py::run_frontier_capped_next_open` | assembled+ohlc输入；按分支真实现金持仓重选；fresh search数量上限；V27 rerank | 本身无12个月限制，适合作为新独立runner执行核；需风险适配与独立review，不能套旧prefix冒充新历史 |

## 立即可实现的首项工作

新增独立的 manifest 驱动历史覆盖审计器 `scripts/audit_bull_bear_history_inputs.py`，只读取冻结原始资料，不调用选股搜索，不触碰生产。首版已实现来源哈希、成员/身份区间重叠、253显式会话、OHLC完整性和单位声明检查；始终输出NOT_ADMITTED。事件、执行域和真实性认证仍属后续任务，不能把结构通过误认为准入通过。

必须检查：

1. 明确交易日历和预热253会话；缺日是缺口，不能仅取最近253条代替253交易日。
2. 每个决策日完整历史成员分母、有效日期与来源；代码更名通过有日期的security_id映射，代码数量不能当公司数量。
3. 每个成员可交易资格、训练数据资格分别记录。新上市不足253日可按既有规则排除，但退市数据缺失不能归入该排除。
4. 对训练与执行OHLC分别验证单位、币种、日期、重复/空值；有拆股事件且价格已复权时必须阻止重复拆股。
5. 执行数据域含退出指数后可能仍持有的证券、并购所得及未到账权益，不能只有当月候选。
6. 事件有效日、换股比例、现金/零股处理、到账/可交易时点和来源哈希。未支持的事件明确阻断；缺价不得填零或永续沿用末价。
7. 输出每个缺口的具体source/日期/security_id及类型；SHA固定来源，报告无“已认证”升级。只有完整范围通过才生成prepared/assembled。

这项工作可先以已有冻结原始资料产生真实缺口报告，随后将其他agent新找到的GitHub数据接入同一输入协议。单一Yahoo路线失败不等于研究阻塞；也不先按候选收益选“好看”的可用年份。

## 接入后的固定执行顺序

来源和覆盖准入 → 新prepared → `compile_monthly_training_window`逐月编译 → V4 assembled → 无搜索技术检查 → 冻结连续起止日、牛熊分期和运行预算 → 连续V27基准 → 一个有机制依据的候选 → `capped_frontier_independent_review.review_book`独立复核 → 同口径年化、最大回撤、恢复期及分期结果。

先从完整可审计的连续历史中选含上涨、重大下跌及复苏的范围；日期选择依据市场阶段与数据质量，须先于候选收益。正式经济运行须注册全新路径及预算，不能使用旧两窗结果拼接。已有固定相对方差方案被否决，不重调窗口追分。

可立即执行的既有接口回归命令（不会跑经济搜索）：

```powershell
Set-Location E:\Git\us_ratchet
& D:\python\python.exe -m pytest tests/test_return_priority_monthly_training_inputs.py tests/test_return_priority_monthly_execution_inputs.py tests/test_return_priority_monthly_execution_inputs_v4.py -q
```

本审计没有执行上面的既有回归命令。新检查器5个测试已通过临时目录直接调用测试函数验证；尝试pytest时解释器返回No module named pytest，没有安装依赖。测试覆盖缺失成员不被删除、身份区间重叠、复权价格拒绝、缺日及来源变化、空研究范围拒绝、结构通过仍不准入；仍须真实来源接入与事件专项验证。

新检查器命令（manifest需由来源适配生成，不使用虚构市场数据）：

```powershell
& D:\python\python.exe scripts/audit_bull_bear_history_inputs.py --manifest <manifest.json> --root E:\Git\us_ratchet --output <new-report.json>
```

## 需要同时保留的限制

当前assembler基础口径仍标记 `CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED`，并明确普通股息未入现金。新来源的下载成功不能自动升级PIT/总回报认证；长周期运行需统一并披露股息处理，若声称总收益则须补全相应账本支持。现有runner仅接受费用/滑点组合0/5或1/10 bps，不能将其描述为汇丰实际费用。未到账权益按用户已确认口径不参与可买资产，但计入总权益与回撤。

当前真正未完成的是历史数据准入和长区间连续验证、以及保年化降回撤目标；这些均与明日开盘无关。真实事件业务验收继续独立等待，不据此停止上述工作。
