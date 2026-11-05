# 动量名单：实际暴露的非股息行动复用边界

仅审查 `tmp/momentum_action_inventory_20261105/inventory.json` 列出的行动，没有经济运行或修改生产/冻结源。结论：五个同SID拆股已有账务与风险换算实现；SMCI跨SID的账务实现已有，但原月风险接口拒绝；SGEN现金并购的账务应收已有，但原月目标provider仍拒绝。不能仅放行gate。

|事件|现有事实来源|实现状态|
|---|---|---|
|NVDA 2021-07-20 4:1|`tmp/qqq_20201231_anchor_20261025/official_split_semantics_batch1.json`：发行人/SEC已保存官方解析观察|同SID split可复用，须注入actions及provider_actions并逐观察配对|
|MNST 2023-03-28 2:1|原`local_split_coordinate_review.json`双行情；本轮补发行人及SEC完成公告，见下|模型已有；原provider事实不能单独当官方认证|
|NVDA 2024-06-10 10:1|同官方batch及`tmp/old_window_exposed_actions_20261026_v1/nvda_split_preparation.json`|同SID已支持；旧preparation只供价格还原，不等于新暴露已准入|
|AVGO 2024-07-15 10:1|`tmp/avgo_independent_20261105/review.json`发行人Q2完成安排及名义坐标抽检|同SID已支持，须配对准确旧SID和原provider观察|
|CTAS 2024-09-12 4:1|`tmp/fixed12_official_actions_20261014_v1/additional_simple_split_web_observations.json`发行人5/2公告，原行情坐标复核|同SID模型已有；现证据是宣布会话与provider一致，非券商实际到账认证|
|SMCI 2024-10-01 10:1且SID迁移|`tmp/old_window_exposed_actions_20261026_v1/smci_split_review_v2.json`，Nasdaq ECA2024-451；法律9/30 17:00、交易10/1|账务及目标provider支持，月风险adapter缺SID迁移；不能沿旧全卖特例放行持有|
|SGEN 2023-12-14每股229美元现金并购|`tmp/sgen_april_action_review_20261026/nasdaq.response`及`official_evidence.json`，ECA2023-721：12/13最后交易、12/14盘前并购|账务merger可终止股份、撤单、计应收；provider不支持merger，风险目标/价格域也需终止适配；没有经纪商到账日期|

## MNST本轮官方补证

[发行人2022年业绩公告](https://monsterenergycompany.gcs-web.com/news-releases/news-release-details/monster-beverage-reports-2022-fourth-quarter-and-full-year)宣布每股增发一股，3/27收盘后派发，3/28开始拆股价交易；[SEC保存的2023年Q1公告](https://www.sec.gov/Archives/edgar/data/865752/000110465923056023/tm2314653d1_ex99-1.htm)确认已按此完成。本轮web搜索返回官方正文解析，不冒充本地原始HTTP文件。另有[OCC 52178](https://infomemo.theocc.com/infomemos?number=52178)交叉确认ex 3/28、pay 3/27及2:1；不是新增现金股息。后续source artifact应固定这些观察与原行情hash。

## 最小合并方案

1. 同SID拆股只建立精确review与execution事件成对清单，复用 `historical_dividend_next_open_book_research.py:280` 的股份/待执行订单乘比率、decision mark除比率，以及 `MonthlyExitCoreResearchAdapter.apply` 的同月peak/last_close同尺度迁移。不得将已复权日线再乘一次。现有 `test_monthly_exit_core_research_adapter.py` 与 `test_historical_dividend_independent_review.py`覆盖阈值/锁和股份订单，但本轮尚未执行测试或真实事件夹具。
2. SMCI复用 `scripts/run_old_continuous_probe_v4.py::reviewed_split_events` 的精确事实/身份验证。独立研究风险薄层需把旧SID peaks、last_closes、unit_ids、exited迁到新SID，价格除10，原月退出锁保留；有新SID冲突或非整数必须拒绝。`backtest/dynamic_risk_units.py::migrate_risk_splits`已有同样语义，但state键是session_date，不可直接当monthly adapter（decision_date）替换。原adapter第37行明确拒绝；原`admit_split_liquidation`只全卖，不能复用为持续持有认证。
3. SGEN原 `continuous_guided_cost_monthly_provider.py:105`对merger返回UNSUPPORTED_EXPOSED_ACTION，必须独立薄层在生效日移除旧月目标及风险跟踪（不是市场卖出、不是止损），保持其他股票峰值/退出锁；账务第314行按229记应收、归零旧股并撤单。现引擎没有现金并购应收到账释放接口，因此最小保守实验可保持应收至窗口末、不可买入，只纳总权益，须显式列为研究假设；不能把12/14完成日自动当可用现金日。若要求到账后再投资，需要新增实际付款证据与接口，不能伪造。
4. 三项独立集成夹具应证明：同SID拆股不假触发20%退出且后续真实跌幅触发；SMCI跨SID保持既有退出锁并可次开盘卖新SID；SGEN生效后无旧价/订单请求，应收不可买且其他目标继续运行。旧源不改，未知行动继续拒绝。gate、股份、目标、风险与独审必须一起接线，避免只有gate通过。

目前不需要扩展ALXN混合并购、AZN转换或其他无暴露行动。上述是最小可运行准备，不代表已经完成新动量账户回测。

## 隔离薄层与三项集成验证

新增 `docs/candidates/momentum_action_bridge_20261105.py`，未修改冻结旧源。`build_provider`仅将现金并购在目标provider私有副本中映射为其已支持的终止目标分支，账务仍必须接收原始`merger`事件，绝不能把映射后的类型传到账务。`ActionRisk`以试算副本迁移SMCI的SID/峰值/单位/退出锁，终止SGEN跟踪，失败不提交风险状态。输出仍是现有target_quantities，兼容独立等权目标。

执行 `D:/python/python.exe -m unittest discover -s tests -p test_momentum_action_bridge_20261105.py -v`：3项通过。它们调用真实monthly provider、原next-open账务、真实月退出核心（仅固定替代昂贵选择），验证同SID20股拆股后真实阈值卖出、SMCI新SID20股实际卖出及原锁不解除、现金并购归零股份且458应收不增加可用现金/不影响其他持仓风险。均为合成小夹具，不是假称真实SGEN付款已验证，也不是完整经济回测。

再次读取SGEN现存Nasdaq原文仅能证实完成、停止交易及229金额，不能证实实际可用现金日期；现存proxy.response是SEC拒绝页面，不能当支付条款原文。故先前“可持应收到窗末”仅是会计诊断，不获准作为完整研究经济口径。明确保留 `CASH_MERGER_AVAILABLE_DATE_AND_RELEASE_NOT_VERIFIED` 启动阻塞；不得以不再投资的任意假设顶替真实付款时序。原provider在新月遇非零应收也仍拒绝，未被绕过。下一步需有限取得现金可用时点依据，并增加明确支付事件/独审，之后才能开启含SGEN暴露的完整账户实验。
