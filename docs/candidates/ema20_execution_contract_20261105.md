# EMA20 独立研究执行合同：固定经济对照已授权，独审后顺序运行

本轮只实现研究adapter与小型真实book集成测试，63日风险预算已收束，根线程已授权独审无阻断后先E1两窗、再E2两窗，最多两个进程并行。E1/E2分别从同一原V27基准运行，禁止叠加63日风险预算、跨月保峰或再入场改良；不改变生产。

## 固定输入与算术

QQQ源、旧manifest哈希核验、重叠开收盘核对和连续EMA代码复用 `scripts/research/ema20_market_states_20261105.py`。alpha=2/21，2020-01-02起首20真实完成收盘SMA种子，之后连续递推、不月重置，首可用日2020-12-31满253会话；80位Decimal，无缓冲/多日确认。源不足或不一致拒绝，不能补值。

经济launcher开始前须再次核原源hash并生成/绑定signal文件、adapter及runner字节。adapter接受的signal是已验证收盘序列，不负责下载或独立证明公开时刻；此边界不能被直接传入未经绑定字典绕过。收盘信号只能用于下一真实开盘。

## 目标与状态

`docs/candidates/ema20_market_adapter.py:Ema20MarketAdapter`继承原 `MonthlyExitCoreResearchAdapter`。每次先以**原月度目标**推进原20%峰值/退出锁，再只对其有效目标施加市场开关。保留原monthly provider状态，市场OFF绝不删除月目标，原退出锁不因市场转ON解除。

- E1 `daily`：QQQ close<=EMA时OFF，close>EMA时ON；下一开盘恢复原当月仍具资格的目标，不日频选股。真实现金不足按原book约束执行。
- E2 `monthly_reentry`：相同离场；OFF跨月保留，只有真实月末决策日且QQQ close>EMA才ON。月末若仍弱，继续持现金到后续合格月末；月初上涨不能解锁。首次窗口锚点按该月末市场信号初始化。
- 两模式在OFF期间仍按原日频推进20%退出状态；因此市场重开时某股可能仍锁定，此为保留V27规则的必然结果，不用现金期间无持股为理由重置峰值。
- 月末即使OFF也按真实分支账户进行原V27月选择并保存目标；下个月恢复使用最新目标，不复用过去基准分支的选择。该设计有计算成本，但避免OFF改变月度状态语义。
- 现金不因月初自动投入；未到账权益仍按原book估值且不可花。原公司行动gate、同SID拆股价格迁移、unsupported action拒绝保持，不因目标为零跳过实际权益核对。
- E2 `month_ends`必须来自完整冻结交易日历的真实月末，不从截断窗口末日推断；2026-07-30不是7月月末。测试中的日期集合为人工fixture，仅验证状态机。

## 可运行接线与已完成验证

复用 `backtest/historical_dividend_frontier_research.py:run_frontier_capped_next_open` 的 `risk=`参数传adapter。没有复制或修改当前运行runner，不使用B跨月保峰runner。选择器/原50%封顶重排保持；原book完成现金、整股、滑点、卖买和股息记账。

`tests/test_ema20_market_adapter.py` 5项通过：

1. 真实monthly provider、callback和book中，仅替换昂贵选股为固定fixture：收盘OFF在次开盘卖出，E1恢复原5股目标，E2跨月仍零，现金非负；初买不是同收盘执行。
2. 个股先触发原20%退出后，市场重新ON仍不能买回。
3. E2的OFF跨月持续，只有指定下一个月末可恢复。
4. 缺QQQ信号拒绝且不推进状态。

这些是因果接线和状态保持测试，不是收益或完整经济独审。初次测试fixture错误固定旧账户权益，原provider准确拒绝SELECTION_EQUITY_MISMATCH；改fixture按真实现金/股数标价后5项通过，未放宽任何生产校验。

## 完整账户launcher（独审无阻断后启动）

`scripts/research/run_ema20_market_20261105.py --window {2021_2023,2024_2026} --mode {daily,monthly_reentry} --output tmp/<独立目录>`。每个模式、每个窗口独立20,000美元账户，费用0、滑点5bp，最多36/31次新月选择，1800秒预算；四条路径不得混合。预算在每次选择前后及逐会话检查，单次同步选择不具强制中断，外部监控不能误称严格1800秒杀进程。复用仅限原baseline保存的完全相同arguments且通过validate_selection_binding的选择，不跨规则盲用结果。

`scripts/research/prepare_ema20_freeze_20261105.py`只生成固定信号及源码hash：`research_contracts/ema20_20261105/{freeze,signals}.json`。从原完整QQQ源生成月末集合，排除源最后截断月，明确2026-07-31为月末而非7/30。来源仍为既有条件性QQQ会话，不声称独立官方交易日历认证；launcher另核原真实月度决策全部属于该集合。

launcher与旧B入口可直接diff：只替换risk为EMAadapter、runner回到原historical_dividend_frontier、增加模式/信号来源/完整月末绑定，保留实际暴露gate。复用已核ALXN一月与AZN补证及既有WBD局部absence，不增加SMCI/ALXN经济适配；新实际暴露无法准入就保存具体失败。输出原book、完整market_audit、月选择/暴露证据、预算与summary，运行末再次校验源码hash。此入口尚未运行经济实验，待launcher独审无阻断后启动。
