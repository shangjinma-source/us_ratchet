# us_ratchet

美股科技篮子棘轮策略工具：支持历史回测、NAV-DD 面板、实盘状态、今日执行建议、战术挂单研究、券商流水导入和前端仪表盘。

## Quick Start

```powershell
pip install -r requirements.txt
uvicorn api.server:app --host 127.0.0.1 --port 8010
```

Then open `http://127.0.0.1:8010/`.

```powershell
# 独立记录一条黄金坑/今日建议快照；不改 config、state 或下单
python -B scripts\advice_snapshot_capture.py
```

建议由 OpenClaw 心跳或 Windows 任务计划每 5--15 分钟调用一次。浏览器关闭
也不会停止记录；脚本失败会返回非零退出码，便于任务计划报警。

## Research Commands

```powershell
# 候选美股池诊断/推荐篮子，不改 config/state
python scripts\universe_research.py --tickers "NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM,MSFT,GOOG,AAPL,SNPS,CDNS" --monthly 3000

# 刷新 Nasdaq-100 官方当前成分、目标产业层价格和版本化候选 registry；禁止用当前成分回填历史
python scripts\candidate_pool_refresh.py --refresh-prices

# 可选：导入 Invesco QQQ 页面 Export data 的官方文件；文件缺日期时才显式填写页面 as-of
python scripts\candidate_pool_refresh.py --local-only --qqq-csv "C:\path\QQQHoldings.csv" --qqq-as-of 2026-07-09

# 首次准备纳指100历史竞争数据：SEC要求User-Agent带真实联系人；显式刷新27期点时成分与历史行情并集
$env:SEC_USER_AGENT="us_ratchet/1.0 your-email@example.com"
python scripts\ndx_competition.py --refresh-history --refresh-prices --lookback-years 2 --top-ns "10" --weight-modes "source_weight" --step-months 1

# 日常只读复跑：约100只当时成分逐股竞争，主目标默认012922，QQQ仅作成分代理和辅助参照
python scripts\ndx_competition.py --lookback-years 2 --top-ns "4,6,8,10" --weight-modes "equal,inverse_vol,risk_parity,score_risk,source_weight" --safe-weights "0,0.26" --rebalance-months "6,12" --max-weights "0.25,0.35"

# v3白盒基线复现：从点时纳指100成分中选股，主目标始终为012922
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v3.yaml --plan-only

# 先跑一个作业检查耗时、CSV和Excel；完成后可随时中断
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v3.yaml --max-jobs 1

# PyCharm中正式断点续跑全部未完成作业；已完成且指纹有效的作业自动复用
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v3.yaml --resume

# 全部作业完成后生成只读决策报告；不重跑回测、不写 config/state、不解锁验证期
python -B scripts\ndx_experiment_analyze.py --experiment-dir data\cache\research\ndx_lab\ndx_012922_price_robustness_v3

# 基于完整v3证据包生成点时相关性簇诊断；阈值仅做敏感性，不是实盘硬规则
python -B scripts\ndx_correlation_clusters.py --plan-only
python -B scripts\ndx_correlation_clusters.py

# v4d 定向复现：只测当前回撤守门的慢恢复，不扩普通价格网格
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v4d.yaml --resume
python -B scripts\ndx_experiment_analyze.py --experiment-dir data\cache\research\ndx_lab\ndx_012922_drawdown_hysteresis_v4d

# 对最差滚动窗口导出逐日 NAV、回撤、目标/实际安全仓和当时持仓
python -B scripts\ndx_profile_trace.py --spec config\ndx_experiment_lab_012922_v4c.yaml --profile dd126_early_5_15 --window-start 2022-12-01 --trade-cost-bps 10

# 基本面第一阶段只做 SEC CIK/Company Facts 点时覆盖率，不计算质量分数
python -B scripts\ndx_fundamental_readiness.py --plan-only
$env:SEC_USER_AGENT="us_ratchet/1.0 your-real-email@example.com"
python -B scripts\ndx_fundamental_readiness.py

# 原始缓存完成后离线重建派生事实，并做 LTM/存量值标准化审计；仍不排名、不回测
python -B scripts\ndx_fundamental_readiness.py --offline
python -B scripts\ndx_fundamental_normalize.py

# 估值二阶升级：先建立带代码生命周期的独立未复权价格，再扩债务直接总额，最后只做值域诊断
python -B scripts\ndx_price_basis_readiness.py --plan-only
python -B scripts\ndx_price_basis_readiness.py
python -B scripts\ndx_debt_concept_readiness.py
python -B scripts\ndx_valuation_readiness.py
python -B scripts\ndx_valuation_diagnostics.py
python -B scripts\ndx_valuation_score_contract.py

# 多股类/ADR身份取证：先看168份实际历史申报计划，再烟雾测试并断点完成
$env:SEC_USER_AGENT="us_ratchet/1.0 your-real-email@example.com"
python -B scripts\ndx_filing_identity_readiness.py --plan-only
python -B scripts\ndx_filing_identity_readiness.py --max-filings 3
python -B scripts\ndx_filing_identity_readiness.py
python -B scripts\ndx_share_identity_readiness.py
python -B scripts\ndx_valuation_readiness.py
python -B scripts\ndx_valuation_diagnostics.py
python -B scripts\ndx_valuation_score_contract.py

# v9：冻结 v8g 组成后，仅测试点时 FCF Yield 的 0/5/10/15% 权重
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_incumbent_v9.yaml --resume
python -B scripts\ndx_valuation_weight_analyze.py

# v10：只惩罚FCF Yield最低30%，不奖励低估值；先续跑，再生成中文配对报告
python -B scripts\ndx_valuation_score_contract.py --score-mode overpay_guard
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_incumbent_v10.yaml --resume
python -B scripts\ndx_overpay_guard_analyze.py

# 版本化产业链 taxonomy v2：先离线核验163个历史ticker、身份有效期和未来数据守门
python -B scripts\ndx_taxonomy_v2.py --smoke --output-dir data\cache\candidate_pools\ndx_taxonomy_v2\smoke
python -B scripts\ndx_taxonomy_v2.py --plan-only --output-dir data\cache\candidate_pools\ndx_taxonomy_v2

# 显式抓取 SEC 原始业务描述文件；只写版本化取证缓存，不自动分类，支持断点续跑
$env:SEC_USER_AGENT="us_ratchet/1.0 your-real-email@example.com"
python -B scripts\ndx_taxonomy_v2.py --fetch-sec --max-jobs 1 --resume --output-dir data\cache\candidate_pools\ndx_taxonomy_v2

# 已完成 SEC 原始文件后，生成中文业务段落证据复核包；只提取候选段落
python -B scripts\ndx_taxonomy_review_pack.py
# Codex 依据 SEC 一手业务段落生成 hash 锁定的审核结果；不读取收益，也不由回测决定风险链
python -B scripts\ndx_taxonomy_v2_apply_review.py
# 将已审核证据送入正式点时 taxonomy 审计；其余行继续 pending/unclassified
python -B scripts\ndx_taxonomy_v2.py --evidence-csv data\cache\candidate_pools\ndx_taxonomy_v2\review_pack\reviewed\evidence_reviewed.csv --output-dir data\cache\candidate_pools\ndx_taxonomy_v2

# 历史业务证据定位只接受 10-K/20-F/40-F；季度申报不会冒充标准业务章节。
# 定位规则变化后的旧抓取保留在 stale_fetch_attempts.csv，原始文件不删除也不参与复核。
python -B scripts\ndx_taxonomy_historical_review_queue.py

# 为当前8只建立独立 SEC 年报/20-F overlay；TSM 不混入历史163 ticker身份，不自动分类
python -B scripts\ndx_incumbent_overlay.py --plan-only
$env:SEC_USER_AGENT="us_ratchet/1.0 your-real-email@example.com"
python -B scripts\ndx_incumbent_overlay.py --fetch-sec --resume --max-jobs 8
python -B scripts\ndx_incumbent_overlay.py --review-pack

# 精确版本化 NDX 年度/临时事件；只抓 Nasdaq 官方来源，支持断点续跑并输出中文审计包
python -B scripts\ndx_exact_events.py --plan-only
python -B scripts\ndx_exact_events.py --fetch-nasdaq --resume

# 量化季度 QQQ N-PORT 代理的滞后与状态误差；QQQ 仍不是候选，不读取收益
python -B scripts\ndx_event_proxy_audit.py --plan-only
python -B scripts\ndx_event_proxy_audit.py

# 生成 GRAL 官方 GIW 证据补录计划；登录 GIW 导出原始文件后再执行导入
python -B scripts\ndx_giw_event_evidence.py --plan-only
python -B scripts\ndx_giw_event_evidence.py --import-export "C:\path\NDXCorporateActions.xlsx"

# 只读诊断当前8只、v8g前沿和v10组件的风格/拥挤度；不晋级、不改实盘
python -B scripts\ndx_style_crowding.py --plan-only
python -B scripts\ndx_style_crowding.py

# 从标准化层使用过的历史 SEC filing header 建立点时 SIC；先烟雾测试，再断点完成
python -B scripts\ndx_sic_readiness.py --plan-only
python -B scripts\ndx_sic_readiness.py --max-filings 3
python -B scripts\ndx_sic_readiness.py

# 只用点时 SEC 基本面和历史 SIC 生成三袖套质量分数；该步骤不读取收益数据
python -B scripts\ndx_quality_readiness.py

# v5 窄实验：固定价格基线，只比较质量混合和 SIC 集中度守门；验证期保持关闭
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v5.yaml --plan-only
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v5.yaml --resume
python -B scripts\ndx_experiment_analyze.py --experiment-dir data\cache\research\ndx_lab\ndx_012922_quality_sic_v5

# 对完整 v5 做替换、三袖套、行业暴露和同窗口结果归因；只描述关联，不调参
python -B scripts\ndx_quality_attribution.py

# v6 有限质量换位诊断：价格 top6 为基座、挑战者限于价格 7~12 名；结果不晋级
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v6.yaml --resume

# v7 核心+卫星复现：唯一 10% 卫星已在 25bp 锁定验证失败；只读重建证据，不写实盘配置
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v7.yaml --plan-only
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_012922_v7.yaml --resume
python -B scripts\ndx_experiment_analyze.py --experiment-dir data\cache\research\ndx_lab\ndx_012922_incumbent_anchor_v7

# v8a 第一阶段：当前8只为主竞争基准；固定等权/安全仓/成本，只筛股票并生成中文报告
python -B scripts\ndx_experiment_lab.py --spec config\ndx_experiment_lab_incumbent_v8a.yaml --resume
python -B scripts\ndx_staged_search.py screen --spec config\ndx_experiment_lab_incumbent_v8a.yaml --analysis-spec config\ndx_stock_screen_analysis_v8a2.yaml

# v8b 第二阶段：股票池已由v8a2冻结，只搜索持仓数量和权重算法；适合在PyCharm终端断点长跑
$v8b = "data\cache\research\ndx_lab\ndx_incumbent_stock_screen_v8a\analysis\staged_search\stage2_allocation_spec.yaml"
python -B scripts\ndx_experiment_lab.py --spec $v8b --plan-only
python -B scripts\ndx_experiment_lab.py --spec $v8b --max-jobs 1
python -B scripts\ndx_experiment_lab.py --spec $v8b --resume

# v8b 完成后：生成中文分析工作簿、前端净值/回撤证据，以及风险预算推导的 v8c 规格
python -B scripts\ndx_allocation_analyze.py

# v8c 第三阶段：只测试源权重单股封顶前沿；先跑1个作业确认，再断点续跑
$v8c = "data\cache\research\ndx_lab\ndx_incumbent_allocation_search_v8b\analysis\incumbent_first\stage3_source_cap_spec.yaml"
python -B scripts\ndx_experiment_lab.py --spec $v8c --plan-only
python -B scripts\ndx_experiment_lab.py --spec $v8c --max-jobs 1
python -B scripts\ndx_experiment_lab.py --spec $v8c --resume

# v8c 分析后只保留精确 Top3 风险包络；后续每阶段都先分析并生成下一份冻结规格
python -B scripts\ndx_cap_frontier_analyze.py
$v8d = "data\cache\research\ndx_lab\ndx_incumbent_source_cap_frontier_v8c\analysis\cap_frontier\stage4_envelope_projection_spec.yaml"
python -B scripts\ndx_experiment_lab.py --spec $v8d --resume
python -B scripts\ndx_envelope_analyze.py

# v8e 逐股组成消融 -> v8f 有界二元搜索 -> v8g 回看期/成本敏感性；均为 research only
$v8e = "data\cache\research\ndx_lab\ndx_incumbent_envelope_projection_v8d\analysis\envelope\stage5_composition_ablation_spec.yaml"
python -B scripts\ndx_experiment_lab.py --spec $v8e --resume
python -B scripts\ndx_composition_analyze.py
$v8f = "data\cache\research\ndx_lab\ndx_incumbent_composition_ablation_v8e\analysis\composition\stage6_pair_search_spec.yaml"
python -B scripts\ndx_experiment_lab.py --spec $v8f --resume
python -B scripts\ndx_pair_analyze.py
$v8g = "data\cache\research\ndx_lab\ndx_incumbent_composition_pairs_v8f\analysis\pairs\stage7_sensitivity_spec.yaml"
python -B scripts\ndx_experiment_lab.py --spec $v8g --resume
python -B scripts\ndx_sensitivity_analyze.py

# 自选分组组合 A/B，对标 012922；默认同时验证 top4/top6/top8 精简篮子
python scripts\target_basket_ab.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --include-voltarget

# 镜像 012922 最新披露 US 持仓子集，扫描 core/W；research only
python scripts\fund_mirror_research.py --fund 012922 --monthly 3000 --top-n 10 --safe-weights "0,0.14,0.26,0.30,0.34,0.36" --core-ratios "0.90,0.95"

# 按 012922 历史季度披露做点时 US 持仓镜像；避免 latest-holdings hindsight
python scripts\fund_quarterly_mirror_research.py --fund 012922 --monthly 3000 --top-ns "4,6,8" --weight-modes "fund_weight,capped_fund_weight,score_risk"

# 只读检查 012922 数据 manifest；仅在明确需要联网重抓时追加 --refresh
python scripts\fund_data_manifest.py --fund 012922

# 012922 固定风格归因：收益风险、行业/区域、现金、集中度与换手；显式 --refresh 才联网重抓
python scripts\fund_style_report.py --fund 012922

# 战术固定限价 A/B：同时输出 vs关闭战术单 与 vs当前实盘战术配置
python scripts\tactical_overlay_ab.py --monthly 3000 --local-only

# NVDA 战术信号点时审计：复用生产信号公式，按每日可用 OHLC 截断，研究只读
python -B scripts\nvda_tactical_audit.py

# NVDA 熊市两臂试探层预注册：固定一股/单周期一股上限，只登记前向观察，不改生产规则
python -B scripts\nvda_probe_preregister.py --plan-only

# 当前8只组合级回调响应审计：逐日截断后复用生产门控/战术函数，不读未来收益、不改实盘
python -B scripts\portfolio_pullback_response_audit.py

# 不固定持仓数量的科技组合搜索计划：1只到合格issuer上限，输出组合空间/剪枝/Pareto契约
python -B scripts\ndx_cardinality_search_plan.py --plan-only

# v11 阶段1当前证券证据包：列出101个真实证券和0/5/10/15%动作；不猜新增资金金额
python -B scripts\ndx_v11_current_valuation.py --prepare-price-plan-only
python -B scripts\ndx_price_basis_readiness.py --plan data/cache/research/ndx_v11_current_price_plan_v1/plan.csv --output-dir data/cache/research/ndx_v11_current_price_basis_v2 --raw-cache-dir data/cache/research/ndx_v11_current_price_basis_v1
python -B scripts\ndx_v11_current_valuation.py
python -B scripts\ndx_current_competition.py
python -B scripts\ndx_marginal_stage1.py --plan-only
# 明确下一笔新增资金后才计算整股数量/实际金额（示例金额仅需替换，不会下单）
python -B scripts\ndx_marginal_stage1.py --plan-only --new-money 3000

# 阶段1不可回填前向链：旧名单只可显式导入为非 fresh seed；未来批次必须当天登记
python -B scripts\ndx_marginal_forward.py register --observation-date 2026-07-13 --import-existing-seed
python -B scripts\ndx_marginal_forward_refresh.py --execute
python -B scripts\ndx_marginal_forward.py evaluate

# 点时动态篮子 walk-forward：每个起点只用起点前历史选篮子，默认含 top4/top6/top8
python scripts\preference_walkforward.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --safe-weights "0,0.26"

# 低频主动重选/调仓成本回放：主动卖出重建仅用于研究，不接入今日建议
python scripts\preference_rebalance.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --safe-weights "0,0.26" --rebalance-months "6,12" --trade-cost-bps 10

# 动态候选篮子实盘准入预检：同时对照 012922 与当前写死配置，不写 config/state
python scripts\live_candidate_gate.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --include-voltarget

# 只读策略研发台账：查看原始阶段、治理阶段、证据完整度和下一缺口
python scripts\research_ledger.py
```

Strategy research scripts are read-only: they do not write `config.yaml`, `data/state.json`, or today's executable advice. Source refresh commands may write only versioned files under `data/cache`.
Candidate admission reads the research-only `research_admission` risk budget: target DD cost uses P50 and the adverse `dd_relief` P10, while the incumbent guard pairs identical rolling starts before taking XIRR-difference P50/P10 and maximum-drawdown-cost P50/P90. Missing tail or paired evidence fails closed.
The CLI labels its incumbent as `config_yaml`; the dashboard API labels a loaded portfolio comparison as `state_cap_total`, so different capital weights are never presented as the same baseline.

## Dashboard / API Notes

- `/api/state` includes `execution`, `explanation`, and `config_health`; research candidates do not feed this endpoint.
- `/api/state.account_readiness` is read-only account/cash readiness context. It reminds the UI that broker holdings and broker available cash must be confirmed before producing share-count buy plans.
- `/api/state.account_readiness.position_gaps` is the authoritative buy-plan account model: only positions with an entry date reduce the live `state.cap_total` target, while book-only shares/value/cost are retained for audit and excluded from real holdings. The browser cash planner also refuses any whole-share order that would exceed cash or the remaining real gap.
- `/api/state.execution_constraints` centralizes the broker execution model from `config.yaml`: venue, lot size, fractional-share support, fee placeholders, and whether cash input is already net of retained cash.
- `/api/state` appends a compact read-only advice snapshot to `data/advice_snapshots.jsonl` whenever the live state payload is generated. Appends flush and `fsync`, `data/advice_snapshots.meta.json` records restart-safe storage health, `/api/advice_snapshots?limit=50` reads only the latest rows, while `/api/golden_pit_review` streams the full journal and deduplicates by session/ticker/source/limit before replaying OHLC.
- `scripts/advice_snapshot_capture.py` is the independent recorder for that journal. It calls local `/api/state`, requires the response's `advice_snapshot.logged=true`, and prints a compact JSON result; it does not mutate `config.yaml`, `data/state.json`, today's advice, or broker orders. Without a recurring caller, no application can record a snapshot while the API is never requested.
- `scripts/advice_snapshot_cron.py` is the deterministic scheduler boundary: it enforces New York weekday 09:00--15:59 with DST awareness, performs at most two bounded HTTP attempts, returns a non-zero exit code on every failed cycle, appends a flush+fsync audit row, and raises `data/advice_snapshot_cron_alert.json` after three consecutive failures. The authoritative Windows task `us_ratchet_golden_pit_snapshot` runs it every 10 minutes; the older OpenClaw `agentTurn` job is disabled because three consecutive turns timed out before the command executed.
- `/api/golden_pit_review?limit=200` replays advice snapshots against later OHLC data to show whether a missed limit was actually touched, how far it missed by, and how 1/5/20 trading-day rebounds evolved.
- `/api/state` 的市场 gate 使用 QQQ/SPY 已收盘日线判定 regime，盘中报价只用于展示/估值/触发；当 `state_freshness.status=DAILY_UPDATE_REQUIRED` 时，当前信号仅为 preview。战术层还会返回 `SUB_LOT_OBSERVATION`，明确低于汇丰整股最小交易单位的金额不是可直接执行的整股订单。
- `/api/daily_update` 只把 state 推进到所有风险腿共同拥有的最新完整日线；美股盘中不会把本地尚未收盘的日历日期写入 state。前端“落盘最新日线”按钮会先要求明确确认，并在同一完整日线重复点击时保持幂等。
- `scripts/advice_snapshot_audit.py` 默认只读审计建议日志；首次接管已有旧日志时，可加 `--repair-meta` 重建侧车的真实行数、首尾时间和无效行计数，不改 JSONL、config 或 state。
- `scripts/advice_snapshot_audit.py` 的默认审计会独立流式扫描完整 JSONL 并对比侧车，不再只回显侧车；`--output` 可原子写入最新报告，`--fail-on-invalid` 会在无效行或侧车漂移时返回非零码。Windows 任务 `us_ratchet_advice_snapshot_audit` 每日 08:30 执行该只读检查。
- `/api/research_candidates?compute=false` returns the fast read-only strategy ledger. Every entry has stable IDs/hashes, hypothesis, data provenance, structured window, point-in-time/OOS status, target/incumbent/risk checks, today diff, rollback readiness, explicit-confirmation state, and a fail-closed governed stage. Use `compute=true` to recompute light sources, and add `include_heavy=true` only when you intentionally want heavier point-in-time and fund-mirror research.
- `/api/candidate_pool` returns the current all-NDX control pool plus the curated strategy target layer. Nasdaq and optional QQQ snapshots have content-hash manifests; price readiness requires at least 504 valid rows and no more than three business days of lag versus the latest local QQQ/SPY date. The current Nasdaq snapshot is hard-blocked from historical backtests; historical competition uses only the separate SEC point-in-time dataset.
- `/api/ndx_competition` returns the read-only Nasdaq-100 individual-security competition report. It restores the last public QQQ N-PORT filing at every rebalance, enforces filing availability and fresh prices, deduplicates share classes by issuer, compares the primary target/current config and emits QQQ only as an auxiliary market reference. QQQ itself is never a candidate.
- `/api/ndx_portfolio_curves` reads the static v8g incumbent-first sensitivity bundle only after verifying that its source experiment completed every job without failure and that the manifest SHA-256 still matches. It never starts a backtest from an HTTP request. The research-center panel plots current-eight, the exact-Top3 baseline, one single-ablation reference, three bounded pair frontiers, and 012922 NAV/drawdown paths, then exposes each solution's latest weights and point-in-time SEC SIC exposure.
- `/api/ndx_style_crowding` reads the static `ndx_style_crowding_v1` bundle only after verifying every CSV sidecar and content hash. The frontend shows the nine diagnostic compositions, real tickers/weights, risk-chain Top1/Top3 and effective-N, 252-day style metrics, and deduplicated unclassified reasons. It never starts a backtest and cannot promote a candidate.
- `scripts/ndx_experiment_lab.py` supports both the historical v3-v7 target-first studies and the v8 incumbent-first staged search. In v8, point-in-time Nasdaq-100 securities are the candidate universe, the current eight-name config is the primary competition benchmark, `012922` is a secondary risk/return reference, and QQQ is only a constituent proxy and auxiliary market reference. The resumable lab writes machine-verifiable CSV evidence plus a Chinese-sheet/Chinese-header `ndx_experiment_report.xlsx`; manifests independently audit weights, holding counts, frozen candidate-pool membership, filing dates, quality/SIC evidence dates, concentration limits, dynamic-signal dates, and modeled costs.
- `scripts/ndx_staged_search.py screen` verifies the completed v8a bundle and exact history/price/quality versions, scores every historical constituent with versioned v8a2 6/12-month forward evidence, and creates sector-balanced 18/24/30-name frozen pools. It writes a Chinese `stage1_stock_screen_report.xlsx` and a generated v8b spec. v8b may vary only holding count and allocation rules inside those pools; no result changes live config or today's advice.
- `scripts/ndx_allocation_analyze.py` verifies the completed v8b bundle and frozen-pool hash, writes a Chinese `v8b_incumbent_first_analysis.xlsx`, replays seven declared return/risk/diversification trade-off paths, and emits the hash-bound curve JSON consumed by the frontend. It also creates the narrow v8c source-weight cap specification; this remains training-only and cannot edit live config or today's advice.
- `scripts/ndx_cap_frontier_analyze.py`, `scripts/ndx_envelope_analyze.py`, `scripts/ndx_composition_analyze.py`, `scripts/ndx_pair_analyze.py`, and `scripts/ndx_sensitivity_analyze.py` form the bounded v8c-v8g evidence chain. Each verifies its completed upstream manifest and audit, writes a Chinese workbook, and generates only the next predeclared experiment. The final v8g report retains three training frontiers but promotes none: every frontier improved the exact-Top3 baseline's XIRR P50/P10 across all nine lookback/cost groups, while no candidate passed the current-eight guard and no fresh locked validation was executed.
- `scripts/ndx_experiment_analyze.py` accepts only a complete lab bundle with comparison-ready phase versions and a passing selection audit. It isolates exploratory training from any executed locked-validation phase, computes training-only cost/window effects, audits locked concentration at its actual cost, and writes a separate `locked_validation.csv` plus the analysis workbook. An executed holdout is marked consumed whether it passes or fails; training seeds remain `STRUCTURE_ONLY_NOT_VALIDATION`, and the report cannot edit the live strategy or recycle validation evidence into training.
- `scripts/ndx_correlation_clusters.py` reuses a complete lab bundle and its exact price-universe hash. It computes 126/252/504-day correlations strictly before each selection date, applies complete-linkage at 0.65/0.75/0.85 only as a sensitivity grid, removes duplicate portfolio states from overlapping windows, and exports cluster weights, pair correlations, persistence, stress dates, plus `joint_decisions/joint_shortlist/robust_family_decisions` that combine target, incumbent, concentration, and cluster evidence without promoting a training shape.
- `scripts/ndx_profile_trace.py` replays one pre-registered profile and exports a daily CSV/Excel trace with risk/strategy/incumbent/target NAV, drawdowns, target and actual safe weights, and the exact point-in-time holdings. It is diagnostic only and cannot change live state.
- `scripts/ndx_fundamental_readiness.py` uses only SEC ticker/CIK and Company Facts evidence. It resumes per-CIK raw downloads, preserves the raw payload hash, models availability as `filed + 1 day`, checks `period_end < selection_date`, and exports numeric facts, concept inventory, and per-selection-date coverage. `--offline` rebuilds derived tables from the same raw bundle without network access.
- `scripts/ndx_fundamental_normalize.py` verifies every readiness manifest and the raw bundle hash, then reconstructs flow metrics with annual plus current YTD minus prior YTD (or four strict direct quarters), same-concept/same-currency prior-year LTM revenue, and instant metrics from the latest eligible balance-sheet date. It exports every signed source component, stale/missing status, unranked quality ratios, integrity failures, and `ndx_fundamental_normalization.xlsx`. Debt aggregation and shares/FX/valuation remain explicit blockers for valuation factors even though research-only quality ranking is now separately gated.
- `scripts/ndx_price_basis_readiness.py` builds a separate, versioned unadjusted-price cache for valuation only and never overwrites the split-adjusted return-engine cache. Price basis v2 preserves the logical strategy ticker while resolving the actual price ticker from a hash-bound CIK+CUSIP lifecycle: four premature META rows use FB and two stale FISV rows use FI. It reuses the 128 verified raw caches, adds only FI, covers 129/129 price tickers, raises minimum/latest point-in-time coverage to 99.01%/100%, and leaves nine acquisition/delisting rows stale rather than aliasing them to an acquirer. All 11 integer-like SEC share jumps still match raw-price split events.
- `scripts/ndx_debt_concept_readiness.py` re-reads the immutable SEC Company Facts bundle without changing the existing quality evidence. It promotes only `DebtLongtermAndShorttermCombinedAmount` as a direct reported total, keeps `DebtCurrent` and `CommercialPaper` diagnostic to avoid lease/subset double counting, and compares every point-in-time row with the prior resolver. The accepted v2 evidence adds 116 strict-complete rows with zero regressions; seven AMD component mismatches explicitly prefer the reported total rather than adding short-term debt twice.
- `scripts/ndx_filing_identity_readiness.py` and `scripts/ndx_share_identity_readiness.py` form a two-step identity gate. All 168 exact SEC filings completed without download failure; the strict resolver cross-checks existing Company Facts values, accepts only issuer-level common shares or explicitly dimensioned common classes, and safely promotes 302 domestic rows. It leaves 160 foreign/ADR rows and four FOX/FOXA multi-security rows blocked rather than guessing FX, ADR ratios, or class allocation.
- `scripts/ndx_valuation_readiness.py` verifies price-basis-v2, debt-v2, and share-identity-v1 manifests before using those 302 promotions. Valuation v4 raises minimum share coverage to 90.20% and minimum FCF Yield readiness to 84.31%, while EV/Sales minimum coverage remains 7.84% because point-in-time debt completeness is still the bottleneck. Live scoring remains disabled.
- `scripts/ndx_valuation_diagnostics.py` calculates valuation values only for readiness-approved rows. Diagnostics v3 exports 2734 FCF Yield values spanning -54.09% to 37.05% and 347 EV/Sales values, with zero unit-review or integrity failures. `scripts/ndx_valuation_score_contract.py` then ranks observed FCF Yield point in time and assigns exactly neutral 50 to all 408 missing rows; every one of the 31 dates passes, EV/Sales remains diagnostic, and no return data is read.
- `scripts/ndx_valuation_weight_analyze.py` is the predeclared paired analyzer for the v9 training matrix. It refuses incomplete or hash-mismatched evidence, compares each 5%/10%/15% FCF Yield profile with the same composition's 0% baseline across all lookbacks, costs, and windows, and writes a Chinese workbook. A passing training weight can only become a locked-validation candidate; it cannot change live configuration or today's advice.
- v9 completed all 9 jobs but no linear FCF Yield weight passed its preregistered robustness gate. `scripts/ndx_valuation_weight_analyze.py` also exports descriptive selection-change and ticker entry/exit attribution. V10's separately versioned one-sided 10% overpay guard passed only the component-relative training gate: all 36 non-zero profiles still failed the current-eight guard, and one-year P10 stability remained weak. The analyzer now writes separate Chinese sheets for composition stability, lookback stability, and absolute admission gates, and returns `COMPONENT_SHORTLIST_INCUMBENT_GATE_FAILED_FORWARD_WATCH_ONLY`. Previously consumed post-2024 evidence is not relabeled as fresh validation; no live setting changes.
- `scripts/ndx_marginal_allocation.py --plan-only` registers the corrected v11 research order: first evaluate one point-in-time candidate using only future contributions while freezing the current eight holdings; only afterward may a separate stage compare whole-sleeve counts 6/8/10/12 with risk-chain, Top3, effective-N, turnover, cost, and liquidity constraints. The plan emits hash-bound CSV/Chinese workbook/manifest artifacts, rejects QQQ as a candidate and ordinary topN grids, reads no returns, and cannot change config/state/today advice. After the event-gap scope package is hash-locked it reports `PLAN_ONLY_PRE_REGISTERED_BLOCKED_UNTIL_FRESH_OOS`; it remains non-executable until fresh forward observations and all event guards permit it.
- `scripts/ndx_v11_current_valuation.py` first locks a 101-security price plan, then consumes an isolated raw nominal-price bundle without touching the adjusted return cache. Current FCF Yield is observed for 78/101 securities; the remaining 23 receive the frozen exact-neutral 50. The v10 overpay contract remains fixed at the lowest-30% one-sided penalty, 10% weight taken only from price, and no cheap-stock reward. `scripts/ndx_current_competition.py` applies that guard after normalizing its score to the 0--1 attack-score scale, uses quality only as the secondary sort, excludes frozen incumbents, duplicate incumbent issuers and unreviewed risk chains, and emits one component champion per accepted risk chain. Historical prices remain signal-formation inputs rather than fresh OOS evidence; event, broker and fresh-OOS gates keep every champion research-only. `scripts/ndx_marginal_stage1.py --plan-only` verifies those hashes and limits 5%/10%/15% actions to the resulting risk-chain champions while retaining the 0% incumbent control.
- `scripts/ndx_marginal_forward.py` freezes stage-1 cohorts in date-specific immutable directories and appends a durable SHA-256-linked JSONL index. Past dates require an explicit imported-seed flag and never count as fresh OOS; a genuine future cohort must use a shortlist whose selection date equals the registration date and must respect the six-month review interval. Evaluation reuses the established monthly rolling convention: offsets 0--5 inside each frozen cycle, 21/63-day diagnostics, a 126-trading-day primary horizon, same-window incumbent controls, versioned 012922 NAV, 10bp costs and exact price-input hashes. P50/P10 and drawdown P50/P90 remain withheld until 12 fresh paired primary windows mature, and stage 2 remains locked.
- `scripts/ndx_marginal_forward_refresh.py --execute` derives its exact ticker scope from the immutable cohort hash chain, refreshes only those security caches plus 012922 NAV, and proves before/after config and state hashes are unchanged. Provider fallback and terminal failure are reported separately. The evaluator exports a separate interim-monitoring sheet while a window is immature; interim marks are explicitly excluded from admission distributions and stage-2 unlocking.
- `scripts/ndx_marginal_forward_daily.py` is the deterministic post-close scheduler boundary for that refresh plus evaluation. It refuses to run before 18:00 New York time, never registers a cohort, writes durable audit/latest-status files, stops evaluation after a refresh failure, and rechecks live config/state hashes. Windows task `us_ratchet_ndx_marginal_forward_daily` runs Tuesday--Saturday at 07:30 Asia/Shanghai, corresponding to the prior US weekday after close.
- `scripts/ndx_challenger_forward_cohort.py` plans and immutably registers monthly pure-equity challenger cohorts. Registration freezes continuous target weights and independently resizes a standardized `$5,000` whole-lot track from the completed observation close; it never reuses historical audit shares or reads the next-session entry open.
- `scripts/ndx_challenger_forward_daily.py` is the fail-closed post-close driver for the frozen 23-candidate registry. It refreshes only the registered 17 equities plus QQQ, registers only when readiness identifies the first eligible completed monthly session, and rechecks live config/state hashes. Windows task `us_ratchet_ndx_challenger_forward_daily` runs Tuesday--Saturday at 07:35 Asia/Shanghai.
- `scripts/portfolio_pullback_response_audit.py` truncates all current-eight and QQQ/SPY OHLC inputs at each signal date, then reuses the production market-gate and tactical-order functions. It reports portfolio-wide WAIT days, same-day pullback pressure, gate distance to MA50, and the latest state-H distance to the first deep-ratchet tier. The 3%/5% fields are descriptive stress labels only; the script does not reconstruct historical ratchet state, read post-signal returns, promote a rule, alter live files, or create orders.
- `scripts/ndx_cardinality_search_plan.py --plan-only` replaces the disabled 6/8/10/12 stage-2 placeholder with a dynamic 1..eligible-issuer contract. It builds a strict-technology primary track and a technology-plus-adjacent sensitivity track from accepted point-in-time taxonomy evidence, keeps every security ID while enforcing one issuer per portfolio slot, and writes exact raw/issuer-dedup combination counts for every cardinality. Spaces above the declared engineering enumeration limit must use an audited multiobjective bounded search; this planner reads no returns and cannot promote or mutate a live portfolio.
- `/api/ndx_marginal_allocation` is a read-only, hash-verifying view of the current 22-risk-chain shortlist, all 67 control/5%/10%/15% actions, incremental-sleeve Top1/Top3/effective-N, the fixed 10bp cost model, explicit blockers, and the immutable seed's forward NAV/drawdown curves. It also verifies the event-gap manifest and exposes the CEG/GRAL cases separately; the frontend now states that GRAL's spin-off addition is supported while its exact removal date remains unresolved. The frontend keeps the current valuation-adjusted structure separate from the older frozen cohort, labels every immature curve `FORWARD_CURVE_MONITORING_ONLY_NOT_ADMISSION_EVIDENCE`, and never feeds this payload into `/api/state` or the buy planner. USD cost and whole-share counts remain blank until `--new-money` is explicitly supplied.
- `scripts/ndx_exact_events.py` builds the versioned NDX official-event registry from Nasdaq annual reconstitution, interim replacement, corporate-action, and special-rebalance sources. It locks source availability dates, effective dates, raw HTML hashes, superseded references, Chinese headers, and future-data gaps; a source available after its effective date keeps historical backtests blocked.
- `scripts/ndx_event_proxy_audit.py` compares that exact-event registry with the SEC QQQ N-PORT quarterly proxy and reports action-level correction lag, report-state mismatches, and unresolved registry gaps. Dataset key `ndx_official_events_vs_qqq_nport_v2` records proxy-extra ticker/name/CUSIP/mapping/weight/value details. The GRAL disposition now distinguishes the official evidence correctly: Nasdaq's then-effective corporate-action rule and 2024-06-05 ILMN spin-off alert support GRAL entering the same index as parent ILMN, while the exact official removal effective date remains unavailable. `scripts/ndx_event_gap_disposition.py --plan-only` therefore records `exact_addition_supported=true`, `exact_removal_date_supported=false` and blocks 2024-06-24 through the audit horizon. It does not infer a removal date from QQQ or secondary media, change the exact registry, treat QQQ as a candidate, or read return data.
- `scripts/ndx_giw_event_evidence.py` closes the remaining GRAL evidence-acquisition gap without weakening that guard. `--plan-only` records the authenticated Nasdaq GIW NDX export scope (2024-06-01 through 2024-07-31). `--import-export` accepts the unchanged CSV/TXT/XLSX/XLS export, preserves a SHA-256-addressed raw copy, normalizes only NDX rows containing GRAL, and writes a hash-sidecar manifest. Every matched action still requires manual classification; the importer cannot promote a removal date, mutate the exact-event registry/disposition, read returns, or enable historical backtests/v11 execution.
- `scripts/ndx_style_crowding.py` runs the read-only style/crowding diagnostic for the current eight, the three retained v8g composition frontiers, and the three v10 guard components. It uses the existing 10bp point-in-time selection snapshots only to reconstruct holdings, then computes strictly-as-of QQQ/SPY/SMH beta, correlations, semiconductor-cycle proxy, stress-window co-movement, marginal risk contribution, risk-chain Top1/Top3, effective-N, issuer concentration, and unresolved evidence. It does not use return results to classify securities, does not promote a portfolio, and writes `data/cache/research/ndx_style_crowding_v1/` with CSV sidecar manifests and a Chinese workbook.
- `scripts/ndx_sic_readiness.py` derives the exact historical filing accessions used by the normalized asset facts, downloads only each immutable SEC SGML header, and records filing date, CIK, four-digit SIC, two-digit group, description, and broad SIC division. It is resumable per accession and explicitly labels SIC as official classification evidence rather than GICS; incomplete header or SIC coverage fails closed. The current evidence bundle covers all 1061 training filings and all 3142 selection rows.
- Historical taxonomy evidence planning now selects only point-in-time 10-K/20-F/40-F business filings. A later quarterly filing can no longer displace an available annual report, and an annual amendment is used only when no base annual filing exists. Superseded quarterly fetches remain hash-preserved in `stale_fetch_attempts.csv` but cannot enter the review pack. The repaired plan contains 112 10-K and 13 20-F locators, with 122 annual filings available within their security identity's observed lifetime; 29 already fetched annual documents remain active and 98 superseded locator attempts are preserved for audit.
- `scripts/ndx_taxonomy_historical_review_queue.py` turns newly fetched historical annual reports into a Chinese, hash-bound manual-review queue. A current-snapshot risk-chain decision may appear only as a routing hint beside the historical SEC excerpt; the queue cannot create accepted evidence, edit either decision registry, backfill a current label, read returns, or admit a candidate. The first complete queue contains 96 pending documents: 88 standardized historical business sections, 65 rows with a current routing hint, and 8 rows requiring source-extraction repair.
- `scripts/ndx_quality_readiness.py` applies a pre-registered 5%/95% cross-sectional winsorization and equal growth/profitability/balance sleeves. Revenue growth and minimum factor coverage are required; R&D and net margin remain diagnostics. The score manifest proves that no return data was read, and live scoring remains disabled even when research ranking is ready.
- `scripts/ndx_quality_attribution.py` verifies the completed v5 evidence hashes, exact quality-score version, and cost-invariant selections before comparing the declared price baseline with each quality/SIC profile. It exports duration-weighted sleeve exposure, exact-date entered/exited sets without inventing ticker pairs, schedule mismatches, paired-window deltas, start-year stability, stress windows, and descriptive Spearman associations. Because rolling windows overlap, statistical inference and causal claims are explicitly disabled.
- `/api/backtest.meta.data_versions` and `/api/rolling_starts.meta.data_versions` identify the exact fund NAV content used by each result. `/api/fund_quarterly_mirror_research.data_manifest` additionally records the holdings-history version, modeled disclosure availability dates, and the point-in-time guard result.
- `/api/fund_style_attribution` returns the fixed 012922 style report: common-window NAV/price risk metrics versus QQQ/SMH/SPY, reported GICS industries, official asset allocation, disclosure-coverage-aware listing-market exposure, concentration, turnover, conclusions, and all input data versions. It is read-only and never feeds `/api/state`.
- `/api/tactical_quality` is read-only tactical-fill quality feedback: filled-price discounts, same-day open/low/close comparison, 20/60 trading-day follow-up, repeat-fill intervals, and current unfilled limit rough opportunity cost.
- The dashboard is split into Today, Account/Cash, Research Center, and Guide pages. Today contains one authoritative cash-constrained share draft; the full strategy-signal table and detailed A/B evidence stay in Research Center.

## Notes

Runtime portfolio state and market cache files are intentionally ignored by Git:

- `data/state.json`
- `data/state.json.bak`
- `data/audit.jsonl`
- `data/advice_snapshots.jsonl`
- `data/cache/**/*.csv`
- `data/cache/**/*.tmp`
- `data/cache/**/*.json`
