# 2026-10-25 源码交付验证记录

首批已发布至 GitHub `main`：[`c242d9a0f963fb8745b385896831281042570863`](https://github.com/shangjinma-source/us_ratchet/commit/c242d9a0f963fb8745b385896831281042570863)。该提交包含本轮源码交付及与原远端 main 的合并，不重写历史。

第二批已发布并远端核实：[`e45df993fc76e422bc2c2ea6cb772e2caad40583`](https://github.com/shangjinma-source/us_ratchet/commit/e45df993fc76e422bc2c2ea6cb772e2caad40583)，包含A拒绝结果、上市资格守门、执行与保存候选审计，以及目标待核验展示修复。

第三批已发布并远端核实：[`1751b7a137593392d1b939c4a94d6dfdee04f6f6`](https://github.com/shangjinma-source/us_ratchet/commit/1751b7a137593392d1b939c4a94d6dfdee04f6f6)，包含窄重排、ETF参照、原生提案接口及文献和结果文档；25个发布文件的Git规范化内容与本地一致。旧远端checkpoint分支仍不存在。

## 实际通过的检查

| 范围 | 结果 | 能证明什么 |
| --- | --- | --- |
| 首次全量 Python 语法检查 | 4,685 个文件通过 AST 解析 | 没有 Python 语法错误；**不等于 4,685 项行为测试通过** |
| 无私人资料的源码 snapshot | 完整导入 `api.server`；首页与 OpenAPI 返回 200 | 新克隆不因缺本机私人部署文件直接崩溃 |
| 未配置业务接口 | 8 个账户、建议及历史研究接口返回 503 / `UNCONFIGURED` | 未配置时不会伪装就绪或创建账户、订单 |
| 隔离 Python 行为检查 | 30 项通过 | 覆盖账户账本、存储、成交与现金衔接、现金变化核算，以及缺失/部分/损坏配置边界 |
| 前端隔离检查 | 4 套 JavaScript 测试通过 | 覆盖单现金入口、资金增减、旧资金恢复、防重复提交、旧建议失效及陈旧余额拒绝 |
| 测试资料脱敏 | 6 个测试改用合成现金和入金，相关测试通过 | 不把真实券商余额或转款金额作为发布的测试样本 |
| 运行源码依赖 | 静态检查的 519 个 Python 依赖在 snapshot 中齐全 | 这些运行入口未缺 Python 实现文件；不代表私人数据、配置或全部动态引用已打包 |
| 远端回读 | main SHA、README Git blob 与本地已发布提交一致 | 首批内容确实已到远端；已合并的旧 checkpoint 分支已移除 |

上述源码 snapshot 检查没有外部网络调用，没有新建数据库，`data` 文件前后相同，也没有写真实账户或重启生产服务。Windows 测试框架内部的本机事件唤醒连接与外部联网分别计数。

部分配置或显式配置存在但资料损坏时仍会失败；不会把原本失败的生产配置静默降为未配置。现有生产旧研究构造代码与参数仅增加条件包围，原块除缩进外保持一致。

## 本轮后续完成的检查

| 范围 | 结果与边界 |
| --- | --- |
| A单向持仓漂移治理 | 两窗完成独立逐日/逐笔复核，合计31次新月度选股，结论为`REJECT`；后窗年化降低13.4846个百分点，仅改善0.2794个百分点回撤。保留现行策略，详见[最终结果](drift_cap_result_20261025.md) |
| 美国普通交易起日守门 | 新增FER/GEHC已知边界、来源SHA和训练情景绑定检查；早窗17个输入受影响、排除18个股票×窗口，后窗无这两个边界的新增排除。只生成研究副本，未重算收益、未改生产目标 |
| 后窗新上市来源 | 五只股票的18个实际股票月份、4,554个收盘及216个情景逐项核对；检查范围内未发现上市前训练或旧代码误拼。完整来源与范围见[复核文档](later_new_listing_source_review_20261025.md)，不升级全域PIT认证 |
| 历史执行现金与退出 | 两窗共645日、80笔成交的现金及费用精确守恒；15次风险退出检查包含一次1股拆为10股的单位重基，4项定向测试通过。卖款依赖不是新增本金或收益损失，详见[执行审计](strategy_execution_audit_20261025.md) |
| 保存候选限仓后评分 | 31次月度选择只复算已有候选及原训练情景；早窗0/19、后窗2/12发现保存的其他篮子裁剪后分数严格更高。来源与资本绑定补核通过，4项定向测试通过；这是训练排序诊断，不是新收益回测，见[详细边界](capped_training_frontier_audit_20261025.md) |
| 窄重排固定经济对照 | 早窗19月完整等价，后窗按新分支账户只做5次新选择；两窗通过条件历史筛选。后窗年化205.3861%→248.7669%，全窗回撤15.1533%不变，成交29→35笔。6组独立复核测试通过；生产尚未采用，见[结果](capped_frontier_rerank_result_20261025.md) |
| QQQ/SPY固定市场参照 | 两ETF×两窗四账，一次运行0.61秒，0优化、socket/DNS护栏0联网尝试；1,290行通过独立单次买入公式，另一个agent未导入脚本或kernel的独立核算也一致，5组测试通过。同日历、2万美元、1bp费用/10bp滑点、不计普通股息，见[规则和结果](fixed_market_reference_20261025.md) |
| 两次重排训练解释 | 24项财富因子、完整评分SHA、逐项省略乘积和平均对数差独立核对一致；另用70位Decimal对数校验，未调用被审脚本或kernel。3组定向测试通过；10/12、12/12只表示固定篮子的省略算术，不是胜率或交叉验证，见[解释](capped_frontier_training_gain_20261025.md) |
| 当前已保存月目标影响 | 使用当时账户、估值及训练输入只读复算98个保存篮子，裁剪后目标不变；1,274项输入源SHA匹配，账户库、目标库和活动配置前后未变。没有用今天余额重选、没有重算退出或今日建议，见[范围](capped_frontier_current_target_review_20261025.md) |
| 原生月目标到独立重排提案 | 纯函数与8组独立合成测试完成，覆盖新证券/旧持仓域、旧仓离开候选池、同分及零键、原0/1bp费率、身份和财务篡改、缺域/时间/单位、纽约估值日期及确定性；真实98篮子的独立公式复核一致。0搜索、0订单、0写账户，保留原始选择；尚未接入生产发布、归档准入或风险域 |
| 默认关闭的隔离提案归档 | 11组功能测试通过，覆盖完整输入/运行源码域、快照、三层身份、提案篡改、路径/别名、原子发布失败、并发占用、幂等及累计字节预算。实际目标的1,274输入源与55运行源码去重为1,309份，58,839,297字节；127.35秒完成隔离原子归档、严格重读与重复写入一致性。原账户库、目标库和活动配置前后SHA相同；内容一致不等于来源真实性或生产准入 |
| 月度目标展示 | 45个控制器场景和4套相关展示测试通过，覆盖初载、失败、失效绑定、成功绑定、20%退出说明及已核验零目标；完整权威月目标域之外的旧仓显示目标0，部分或缺失映射保留待核验；表格与两条K线传递路径均不再回退到未限仓数量 |
| 静态上线内容 | 首页与4个修改的JavaScript模块只读GET返回200，逐字节等于工作区；4个模块和首页内联脚本语法通过。没有重启服务或调用账户写接口 |
| v26现金与等待状态调用链 | 只读核对17份源码及单现金、目标待核验、真实成交承接路径；纯函数反例确认WAIT不生成订单并隐藏旧退出日期，未证明旧projection造成用户可见或交易缺陷。0账户/目标写入、0重启、0生产preview POST；这不代替周一实盘验收 |
| 盘中UI验收器兼容 | V2修复缺限仓映射时回退原数量、完整映射之外旧仓目标0被误拒，以及HOLD状态额外可见买单漏检；22项定向检查通过（10项V2、12项原V1）。98项月度任务源码pin仍匹配，V1、生产服务与任务配置未修改 |
| 月底与新月时点 | 现有本地日历指向北京时间10月31日04:00收盘准备、11月2日22:30开盘，23:00后允许采用资料；现有15分钟任务的名义首轮为23:14。自动任务采用资料不生成目标，新月目标另由用户正常现金按钮触发；只读采集仍拦截目标生成，未把静态审查算作换月验收 |

## 尚未完成或不能据此宣称的事项

- A首次固定运行的`FAILED_INCONCLUSIVE`记录仍保留；v2只修独立复核中的等待日断言，早窗零搜索复核后完成剩余后窗，最终拒绝A。不能把原失败批次改称通过，也不能将研究源码交付写成策略已采用。
- 现行方法先选股评分，再加50%数量上限；裁剪后排名不保证不变。先前可行性与保存候选重评分只是诊断；后来完成的窄重排双窗经济对照通过历史筛选，仍未生产采用。它不证明全域约束最优、未来收益改善或最大回撤降低。
- 语法检查、隔离测试和源码推送不能代替真实盘中、下一笔策略内真实成交、月底准备及新月采用验收。
- 历史回测的数据口径、下一开盘成交及卖款可用假设仍有边界，不能表述为独立样本外证明或未来收益承诺。
- 早窗源清单明确为 `FIXED_CURRENT_OBSERVED_101_SURVIVOR_BIASED`，并标记 `full_pit=false`；使用当前观察名单回看历史会产生幸存者偏差。年化只是该区间的日历天数折算，不是收益预测。
- 当前50%限制作用于月度目标配置；价格或现金变化后实际权重可以超过50%。20%为单股月度收盘峰值退出阈值，不是组合最大回撤保证。这两项解释已按当前风险模块与目标数量计算代码核对。
- 未运行整个历史测试库；不能以本页的已验证范围宣称全部历史脚本与实验都已验收。

## 本机证据位置

以下文件保留于执行机器，不随 GitHub 源码发布；它们是本轮检查记录，不是新克隆的运行依赖：

- `tmp/source_release_20261025/full_python_syntax.json`
- `tmp/source_release_20261025/checkout_fixed_startup_and_tests.json`：最终有效的 30 项 Python 与完整应用检查。
- `tmp/source_release_20261025/checkout_isolated_tests.json`：其中四项 JavaScript 结果均通过；早期 Python 运行曾被测试网络拦截器误挡本机事件唤醒连接，已由上项最终结果替代，不计为通过。
- `tmp/source_release_20261025/synthetic_cash_sanitization.json`
- `tmp/source_release_20261025/checkout_closure_audit.json`
- `tmp/source_release_20261025/legacy_constructor_preservation.json`
- `tmp/source_release_20261025/checkout_partial_environment.json`
- `tmp/source_release_20261025/remote_release_readback.json`
- `tmp/source_release_20261025/monthly_cap_display_readback.json`
- `tmp/source_release_20261025/v26_cash_wait_readonly_review.json`：当前调用链、源码SHA与WAIT反例。
- `tmp/source_release_20261025/upcoming_acceptance_compatibility_review_v2.json`：最终22项UI验收器检查、98项任务pin与月底/新月时点核验；原21项记录保留。
- `tmp/source_release_20261025/third_release_remote_receipt.json`：第三批远端提交及25文件内容回读。
- `tmp/drift_cap_research_20261025/later_completion_v2/terminal.json`
- `tmp/strategy_mechanism_review_20261025/drift_complete_results.json`
- `tmp/strategy_execution_audit_20261025/report_v2.json`
- `tmp/capped_training_frontier_20261025/`：保存候选诊断及来源/资本绑定补核。
- `tmp/capped_frontier_rerank_20261025_v2/`：窄重排固定登记、运行、独立复核及保存账本分析；首个技术预检失败另保留于无v2后缀目录。
- `tmp/capped_frontier_rerank_20261025_v2/training_gain_independent_review.json`：两次实际重排的24项训练解释独立核对。
- `tmp/capped_frontier_current_target_20261025/`：当前目标的私有原始快照、98篮子及1,274项源绑定复核；不发布账户金额、股数或身份。
- `tmp/capped_frontier_current_target_20261025/native_proposal_independent_review_v2.json`：最终8组桥接边界及98篮子独立公式复核；原v1记录保留，不代替生产准入或行情真实性认证。
- `tmp/saved_frontier_archive_native_20261025/validation.json`：实际目标1,309来源的隔离归档、重读、幂等与生产文件前后SHA；归档原文均留本机。
- `tmp/saved_frontier_archive_native_20261025/independent_content_review.json`：不导入归档模块的独立内容复核，1,317文件及完整身份链匹配；当前受保护文件与执行方操作后记录一致。
- `tmp/market_reference_20261025_v1/`：四本固定ETF价格收益账、登记、独立公式复核和零联网记录。
- `tmp/known_us_boundary_review_20261025_v2/`
- `tmp/later_new_listing_scope_20261025_v1/`：审查脚本与完整逐项结果仅保留本机，公开文档不等于GitHub已包含完整复现包。

## 第五批：保存提案的隔离完整预览

来源核验6组、风险读取8组、全链预览9组通过；最终历史账户绑定修订定向复核2项通过。7个最终文件SHA与本地验证凭证一致，6个Python文件语法通过。实际解析、账本、风险存储与执行桥接运行；行情传输为合成字节，网络和新训练入口被禁用。覆盖非空买卖、已有退出、未完成订单、现金不足、并发变化、月切与过期报价。无真实账户或生产目标写入，无新经济搜索。

实现与限制见[隔离链说明](saved_frontier_isolated_pipeline_20261025.md)。验证凭证仅本地保存：`tmp/source_release_20261025/saved_frontier_pipeline_validation.json`。23组测试不代表现有V7、前端或真实市场来源已经接通。

## 后续定点修复与只读证据

- 隔离链最终返回有效期修复：新增1组测试含报价到期、信号到期、时钟回退3个反例通过；正常买卖（0/1bp）和OPEN等待2组复核通过。未重新跑全23组或收益研究，不把定向复核数量累加成全量验收。凭证：`tmp/source_release_20261025/final_return_expiry_validation.json`。
- 生产返回链静态核对：V26外层来源及账户复核后检查报价，写日志后再次检查；买卖报价期限不晚于会话收盘，前端按期限隐藏。凭证：`production_final_expiry_audit.json`，不代替盘中验收。
- 真实来源局部核对：`frontier_real_domain_comparison.json`、`frontier_historical_account_reconstruction.json`、`frontier_identity_byte_closure.json`。覆盖价格、历史版本及已有持仓源字节，不宣称完整新提案审核。
- 原Goal完成性仍未证明：`goal_requirements_completion_audit.json`分别列出隔离证据和缺失的真实事件。以上未写完整路径的凭证均位于本机`tmp/source_release_20261025/`，不随源码发布。
