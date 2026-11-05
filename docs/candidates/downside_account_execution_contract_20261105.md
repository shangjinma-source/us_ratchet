# 同次候选下行约束：固定账户对照执行合同草稿

状态：未启动。候选runner入口强制 `DRAFT_PENDING_INTEGRATION_AND_ACTION_REVIEW`，待根审阅与必要集成验收后另行冻结。用户已明确暂不限制持股数量，不能再把5/10只澄清作为推进依赖。

## 固定经济规则

- 两独立窗口：2021–2023、2024–2026-07-30，初始可交易现金各20,000 USD；0佣金、5bp next-open滑点，保留现有股息/公司行动账户、原月度20%退出及当月再买限制、原50%单股整股上限。
- 唯一变化：原8192评估预算+32步连续候选完全不变；观察同次成功评估候选，cap50/去重后以252日价格收益的 `D(P)=mean(min(rP,0)^2)<=D(QQQ)` 筛选，再按原12情景精确财富乘积评分。每月 `max_holdings=len(当月可选域)`，风险计算最多10,000个去重篮子；达到上限即拒绝完整结果，不将前缀当全部候选。
- incumbent固定为**实际V27 saved-frontier cap50 rerank最终篮子**，不是raw selected直接cap。它通过D门槛时，仅产品严格增加才更换；同分保留原篮子。其不合格时从合格域（含现金）依原产品、低notional、字典序择优。此定义与此前静态raw-capped规则有别，开始前固定，不据成绩选择。
- 原资本绑定函数从本分支当时现金、实际股数、决策报价计算权益；候选权重、搜索及整股配置必须随新账户变化，不能拿baseline财富/旧目标替代。训练资料可同日复用，但真实SID与全部253训练价格必须存在，12情景逐项匹配。实际QQQ两源重叠必须一致。
- 不叠EMA、63日波动缩仓、跨月保峰B、SMCI风险身份适配或新财报评分。训练下行矩并非未来最大回撤保证；结论须两个完整账户窗与同费用含息QQQ、V27对照，同时报告2024–2025剔除2026片段。

## 最小接线与文件

- `docs/candidates/downside_account_selection_20261105.py`：复制原资本状态翻译薄层，调用已验observed搜索及integer observer；旁路保存sidecar。保留原金融校验，单独应用D筛选；新研究source pins必须另行绑定，原V27 pins不能认证新算法。
- `scripts/research/run_downside_account_candidate_20261105.py`：由风险预算runner缩改；独立加载已冻结book kernel模块实例，原MonthlyExit、next-open账务及行动gate不变。只修改选择callback；全部新输出用 `RESEARCH_EXACT_FRACTION_HEX_JSON_V1`，原失败输出不覆盖。
- 原输入：两个baseline `execution_inputs.json`/完整book；对应trend execution_inputs里的action_review；execution_prices_v1；已审 `equal_four_20261105/source_review/admitted_supplement.json`。后窗沿固定WBD absence adapter。新增研究模块、codec、observer三副本、数学helper与原依赖须在正式冻结manifest全部绑定并启动前/结束后核验。

## 预算与恢复

- 固定每窗10,800秒、每月600秒、早/后窗最多36/31次新选择；合作截止在每observer调用入口/返回及book provider执行，单次原子算术可能稍越截止，不能宣称硬实时。失败与续接累计预算不重置。不扫参数、无自动重试。
- 这是执行上限，不是预计完成保证：完整首月实测约244秒，后续不同权益/支持数会变。并行会改变耗时。输出完整月选择/sidecar/源hash/PID/预算，失败保存reason与已完成账本；不因研究结果差而提前停止另一窗。
- 首月已验缓存只有当完整account arguments、有效search arguments、source pins、QQQ/训练坐标、sidecar完整覆盖及独审hash完全一致才允许复用。日期相同或仅目标相同都不足够。当前草稿**没有缓存复用/恢复入口**，先重新搜索路径可执行性验证；正式执行前根决定首月充分审计与缓存准入。原审计验证每k赢家可行性+覆盖汇总，不独立证明赢家支配所有已访问候选（全ledger未持久化），此限制必须保留。
- 续接须新目录指向父contract/sourcehash；之前完整选择只在全参数相同时复用，累计new/reused/wall seconds继承。重复执行账本时核父已完成ledger前缀逐字段一致；不得复用原baseline旧财富选择。

## 开始条件与明确未完成

1. 根及公司行动agent完成宽篮子暴露边界预检，特别ALXN混合现金/换股未到账分账、AZN ADS变更、SMCI持仓跨身份。当前原gate阻断不能靠“零持仓审计特判”替正持仓放行。资料缺口保留阻塞，不能假设交割。
2. 合成真实book集成验证：动态财富传递、cash fallback、incumbent同分保留/不合格替换、sidecar证据绑定、next-open/股息/退出锁不变。现 `tests/test_downside_account_candidate_20261105.py` 的4项合成集成已通过：真实资本wrapper动态权益110→220；真实book股息后权益110→609.975、next-open买5/买25/原20%退出卖30；同分留存、全现金与跨月/权益/坐标/quantity/score污染拒绝。此通过仅覆盖小夹具，不能代替两窗实际公司行动与经济验收。
3. 新版本独立冻结manifest与完整依赖闭包；核所有输入的已有预期hash，非自算hash冒充外部认证。草稿运行阻断保持到该步骤完成。
4. 独立账户审阅器适配新的目标机制及版本codec；最终每窗完整session、选择次数、现金/股份/股息/收益/风险生命周期核过，才能发布经济指标。完成一窗即独审，不等待另一窗。

本轮仅交合同及实现草稿，不运行账户回测、不改生产、不改变任何真实账户。

公司行动只读审阅补充：`tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json` 的9股息与ALXN/SGEN精确无行动区间尚未接入本草稿。它是训练因子证据，须逐事件核金额/单位/ex/pay/执行schema后转换，不可直接作为账本事件或放行全部合并；ALXN/AZN复杂行动与SMCI持续持仓身份迁移仍硬阻塞。用户授权研究已存在，运行guard代表技术验收未完成，不是再次索要授权。

sidecar接线现绑定实际资本decision/binding、canonical动态search arguments、原与研究source pins、stock/QQQ日收益坐标。raw另外记录sidecar digest；apply同时核匹配并重算各保留篮子cap/精确评分/现金/下行门槛。摘要不是外部来源认证；调用方仍必须按冻结manifest核实际字节。

2026-11-05根复跑tests/test_downside_account_candidate_20261105.py：4项通过（0.103秒）。runner仍以DRAFT_PENDING_INTEGRATION_AND_ACTION_REVIEW拒绝长跑；这是待完成技术接线，不是缺用户授权。
