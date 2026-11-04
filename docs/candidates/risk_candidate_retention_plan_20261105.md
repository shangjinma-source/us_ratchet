# 同次已评估候选的下行合格保留：最小接线计划

状态：仅只读代码审阅与设计，未修改搜索、生产或启动经济回测。持股上限 `max_holdings` 必须由外部明确提供；本文不代用户选5或10只。

## 实际丢失位置

1. `backtest/research_exact_fast_search.py::search_fresh_cash_quantities.evaluate` 按 `(12情景精确财富乘积, -notional, signature)` 排序，`best_by_k[k]` 只保留一条。已评估但增长较低的同k低风险篮子被丢弃。内部 `objective_products`/`visited` 虽暂存所有评估签名，却未作为结果输出。局部搜索的 `anchors` 又从该增长最优条目取得，故搜索方向本身也偏增长；不能把结果稀少归因于保存一层。
2. `backtest/saved_quantity_candidate_comparison.py::compare_saved_candidates` 仅接收上一层 `best_by_k`，新增连续候选经 `evaluate` 后再次每k只留增长最优。`additional_generation` 保留生成器候选，故连续新增部分可另审；不能据此恢复第一层已丢的局部/种子候选。
3. `backtest/research_exact_fast_guided.py::enhanced_search` 将第二层 frontier 写入最终结果。`backtest/capped_frontier_rerank_research.py::rerank` 才执行50%整股裁剪和重评分：原增长最优未必是裁剪后最优，更未必满足下行约束。`core/saved_monthly_frontier_proposal.py::build_frontier_proposal` 也仅消费该每k单条结构。

已有67月静态结果只证明“保存下来的增长frontier”存在宽篮子偏好，不能证明完整访问域内无小篮子合格解，更不能证明所有未访问组合无解。

## 唯一建议：只加观察钩子，先不改搜索路径

在独立研究版本的两处 `evaluate` 完成合法性与原增长计算后，向可选 `candidate_observer` 发送不可变签名及来源序号；不读其返回值，不改变 `best_by_k`、anchors、种子、配额或停止规则。默认无钩子时返回必须逐字节等同旧结果。两层共用本次调用的观察器，第一层被第二层重新评估的签名去重。

观察器按原50%整股规则裁剪、去零、去重；仅当裁剪后正持仓数≤外部 `max_holdings` 时计算252日下行矩（现金单列始终保留）。以本次真实输入价格/可交易权益构造权重，核同日253价格、12情景和source pins，复用已验严格上下界比较与边界Fraction精确回退；门槛仍唯一 `D(P)<=D(QQQ)`。原始raw产品不能代替裁剪后产品，裁剪后必须调用既有精确12情景评分。

仅保留每个实际k的“下行合格且原评分最高”记录及现金，已经足够服务这个固定门槛和既定排序，无需新造多目标优化器或任意top-N截断。选择时保留已合格原篮子的原严格改善/同分约定；其余合格篮子按原排名。风险阈值、持股数要求和现金不能事后为改善成绩更改。

独立sidecar建议结构：`binding={search_arguments_sha256, training_prices_sha256, qqq_sha256, source_hashes, max_holdings}`；`coverage={raw_unique_observed,capped_unique,over_holdings_limit,risk_evaluated,risk_pass_positive,risk_pass_cash,exact_boundary_count,complete}`；`eligible_best_by_k[k]={target_quantities, actual_k, notional, residual_cash, exact_score_binding, downside_interval, comparison_method, source_phase, source_evaluation_index, raw_signature}`。旁路输出，不伪装为原 `best_by_k`，不让原source校验误认证研究附加结果。

## 成本与失败边界

设原唯一评估数E，裁剪后符合上限的唯一数U，持股上限H：原12情景路径不变；附加评分约O(U×12×H)，下行约O(U×252×H)有理数运算，位长会影响实际成本。若保留完整raw签名，记录/去重上界为O(E×N)，N为原证券域大小（原候选可能超过H）；仅合格裁剪签名为O(U×H)，获胜记录O(H²)，252日输入O(252×证券数)。这不是零成本日志：已完成静态预检只处理67个月保存域也耗时467.8秒，不能承诺观察所有搜索状态仍等速。应先单次有界夹具/代表月记录U和耗时，不直接启动67月全经济回测；观察预算耗尽须 `complete=false` 明确失败，不能把部分样本标完整或悄悄截断。

必须验证：开启/关闭观察器原访问顺序、评估计数、selected及best_by_k完全一致；同k增长第二名满足D而第一名失败能留下；raw到cap后名次反转；跨两层重复仅算一次；0目标不算持股；恰好等于门槛精确通过、边界无法浮点放行；日期/证券域/源hash缺失拒绝；全部正仓失败时仅现金且单独统计；观察器未覆盖完整调用不得发布完整结果。

该步骤只是扩大保留同次已评估候选，并非风险感知新搜索。若它仍只留下低收益/大现金小篮子，下一阶段是否改变种子或搜索目标必须另立合同：不能在这里偷偷加入风险优化邻域，更不能从旧best_by_k回放推断未保留候选的结果。任何账户实验仍需按新分支财富重新选股，保留公司行动与独立账务审核。

## 隔离组件已实现（尚未接搜索）

新增backtest/downside_candidate_observer_research.py，max_holdings与风险计算预算均须显式传入。复用原50%裁剪、12情景精确评分、252日严格下行矩比较；验证同日收益与12情景一致。10项夹具测试通过，覆盖增长第二名留存、裁剪后名次反转、跨阶段去重、精确边界、现金、预算及异常不可逆失败。现金fallback独立于搜索观察计数。

finalize仅证明已观察流结束且未发生预算/校验失败；source_authenticated与search_coverage_verified均为false，不能视作完整搜索或来源认证。尚未接入两层搜索、尚未验证访问顺序/预算/原结果不变，尚无代表月成本及账户收益证据。不得据10项测试宣称策略进步。当前仅合成夹具使用显式持股上限，没有替用户选择实际上限。

## 两层隔离接线已验证

新增research_exact_fast_search_observed、saved_quantity_candidate_comparison_observed、research_exact_fast_guided_observed三个研究副本，仅变更来源hash注释、可选参数、观察钩子及导入传递。原三份文件未改，头部来源hash逐项核对。tests/test_downside_observed_search.py三项测试通过（根独立运行2.213秒）。测试使用sys.setprofile独立捕获原始evaluate更新visited/cache后的返回序列；原始、无观察器副本、有观察器副本逐字段结果、全部候选访问顺序及计数一致，连续阶段确有新增候选。两阶段异常传播及原搜索预算不足保持未完成均验证。

这些是三股票合成夹具，不代表真实月运行成本或经济收益。原返回字段及REQUIRED_PINS保留仅用于等价验证，绝不能认证新研究副本；后续真实数据sidecar必须另外绑定三个新副本、观察器、输入数据及数学依赖的hash。持股上限仍待用户选择，未启动代表月份或全窗口回测。

## 首个真实月份的有界成本检查

固定最早2020-12-31，训练2020-01-02至2020-12-31、102证券；不是2020年实际账户回测。原8192评估预算及32连续迭代保持。诊断持股上限取完整102域仅避免按未知偏好过滤，不代表采用102只持仓。风险最多64次，合作截止180秒，单次运行68.341秒完成（加载1.262秒），原search_result与历史保存结果完全一致、diff为空。

实际base评估8091，比较阶段97条既有+22条新连续候选；hook8210次，raw去重8113、cap去重7124。风险仅64次，观察状态不完整，finalize拒绝INCOMPLETE_RISK_OBSERVATION_BUDGET。63个正仓样本与现金通过仅是访问前缀，不是最佳候选、不评价收益或全域覆盖。未分别计时risk，不能从68秒估算新增开销或线性推算全量。

结束后1516文件hash重核通过，根再次独立核验。证据tmp/downside_observer_cost_first_month_20261105/{summary.json,saved_result_differences.json,post_run_source_verification.json}，脚本scripts/research/sample_downside_observer_cost_20261105.py。无账户写、模型或生产改动，无第二次运行。当前不足以证明全窗口风险观察预算可承受，完整研究仍需明确持股偏好并设定覆盖预算。

## 精确日收益算术加速候选（未接观察器）

新增downside_daily_integer_candidate.py：按同一月每日日收益系数取共同分母，候选只做整数加权后构造Fraction；下行矩及阈值不变。调用者仍须认证日期/证券/来源，本纯算术组件不做来源准入。固定最早月份已存best_by_k按k排序裁剪去重前64篮子（不同于前次64个搜索访问前缀），两轮交替原/候选，32256个日收益Fraction逐值完全相等。原1.348/1.326秒、候选0.412/0.437秒，约3.15倍仅指加权算术；构造0.147秒，整数及容器约15.77MB，最大分母4677bit。

两项边界测试通过，完整成本检查5.39秒，无搜索/账户回测。下游classify用合成负1%参考验证同值，不是QQQ风险筛选或经济收益。未分别证明小篮子、全102域或完整回测速度。尚未接入观察器，原生产和冻结脚本未改。证据tmp/downside_integer_cost_20261105/result.json，源文件hash完成后根再次核验。

## 整数观察器接线

新增隔离downside_candidate_observer_integer_research.py，仅在原观察器初始化预计算整数系数、替换日收益加权算术。12项边界与两阶段合成搜索测试通过，完整sidecar、原搜索输出、raw/cap集合及失败状态一致；原观察器保留不改。接下来单独固定首月做完整观察可行性检查，至多10000风险计算/300秒，不运行账户，不替用户选择实际持股上限；失败不自动重试。

## 首月完整计算完成但落盘失败

完整观察单次运行243.260秒，其中observer累计222.890秒；8210次hook、8113个raw、7124个cap全部计算风险，10000预算未耗尽，原search_result逐项相等。1518来源hash运行后及根复核均通过。然而保存每k候选sidecar时，Fraction十进制字符串超过Python4300位限制，进程已结束，sidecar未生成，summary状态STOPPED_WITH_ERROR。不能宣称完整交付，也无法从已保存原搜索结果恢复丢失的观察器最优候选。未重跑。

已准备research_exact_fraction_json.py及独立v2 runner：分子/分母采用版本化十六进制对象，无损解析，不改全局整数限制，不用浮点近似。两项测试含超过5000十进制位的分数与嵌套/符号/零/版本拒绝。v2所有JSON为encoding+payload包装，须用该codec.loads读取；新输出目录独立，未运行。原失败脚本字节及证据保留。后续若执行v2是明确的新尝试，不能称续接已退出进程或无新增计算。

## 序列化修复后的单次重试及独审通过

v2在243.790秒完成并保存sidecar，observer累计223.385秒；1519来源hash通过。原search逐项一致，8210hook、8113raw、7124cap全量风险计算，无预算遗漏。只代表同次已访问域完整，不是所有可能组合。保留现金及实际持股数1—96各一条，97—102未留合格赢家不证明全市场无解。

独立脚本review_complete_downside_observer_20261105.py用原逐项Fraction收益与真实QQQ精确下行矩重算97条，核253日/12情景、cap/整数/issuer/现金/评分和汇总计数，24.269秒PASS。新保留路径覆盖7061个正仓合格篮子及现金，其中6967个合格签名未在旧cap frontier保存；单股397、双股29均被旧保存域遗漏。该月份实证支持扩大候选保留的必要性，不证明账户收益、熊市表现或所保留赢家全域最优；未保存全部访问候选ledger，独审不宣称逐项证明赢家支配所有候选。

证据目录tmp/downside_observer_complete_first_month_20261105_v2，包含版本化summary/sidecar/independent_review；旧失败目录不变。这是明确一次修复后重试，没有增加月份、改参数、选择用户持股限制或运行账户回测。
