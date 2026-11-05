# 拆股后日线读取与建议组合：隔离候选验收

状态：本单元部分完成，未接生产；不能据此宣布原 Goal 完成。

## 实际交付与验证

- `split_saved_frontier_daily_evidence_20261105.py`：完整隔离 reader，复用现有 `split_monthly_raw_history_20261105.normalize_monthly_raw`，不新增价格归一算法。
- `split_saved_frontier_daily_composition_20261105.py`：完整隔离 composition，旧 target/proposal 原文和标识不改；独立 transition 验证后才进入原报价、公司行动审阅、限价与差额计算。
- `tests/test_split_saved_frontier_daily_20261105.py`：3 个综合测试，agent session 13792，exit 0，67.720 秒。根线程另外独测，结果以其记录为准。

六条真实模块组合路径：正现金买卖；零现金仅卖；买入分钟行情拒绝后的可卖部分；追加现金确认后刷新；追加实际账本卖出及现金确认后刷新；拆前 A 持仓 2 股经真实拆股账本变 16 股、原风险退出仍保留并生成卖出 16 股。

测试实际使用 native archive/proposal、SplitStrategyAccountStore、project_native_split、prepare_split_risk、MonthlyPeakExitStore、市场数据解析、行动审阅、执行限价与差额计算；不是 stub signal。缺买入行情分支通过模拟已有 MINUTE_GAP 错误进入，后续卖出仍经过真实组件。来源字节/身份、行情和账户全部为临时合成夹具，网络明确禁止，不能解释为真实供应商或真实账户验收。

AS_TRADED 与已复权 close 两种输入得到相同风险结果，已复权不二次除；拆前退出状态保持。未知 basis、分离时钟、ledger 确认晚于 now、review 声称早于 ledger 确认可交易均拒绝。固定准备的 transition 通过实际账本前缀重放认证；后续现金/成交可继续，但后续新拆股必须重新准备。所有六路径断言原准备 payload/digest 不变，原账户不被 preview 修改。

## 明确未完成

1. distribution 与 quote 生效时间分离时明确拒绝；未实现完整三时钟方案。
2. 隔离补采 transport→重叠审阅→reader/risk 已接通并独测；生产自动调用与配置尚未接入，见末节。
3. 缺真实供应商 split-adjusted/as-traded 口径认证；不能从 adjclose 或价格跳变推认证。
4. 未修改生产 pinned source、8010、真实账户、金融任务，未激活生产；AI 真实模型复核不在本测试中。
5. 未完成实际拆股前后连续运行/自动补采端到端验收。普通无拆股入口未在本次重新测试。

## 补采入口与当时接线计划（已完成的隔离部分见末节）

当前 `data/saved_frontier_live_reader_v1.py` 的调用链：
`prepare_frontier_supplement_request` → `strategy_monthly_supplement_gzip_v1.capture_supplement` → `saved_frontier_source_reader_v1.read_frontier_capture` → `saved_frontier_capture_review_v1.review_supplement_packets` → `saved_frontier_first_window_v1.review_first_window`，然后 `saved_frontier_source_review_v1.review_proposal_monthly_sources`/`frontier_monthly_peak_raw_history_v1.review_monthly_supplement`，最后 `apply_frontier_exit_packet`。

真实阻点在 first-window 的原单位 baseline 重叠检查，以及 supplement reviewer 调用旧 `monthly_peak_raw_history.normalize_monthly_raw` 后按原数值直接比较 overlap。旧单位价与新单位价不能直接比，也不能删除该连续性校验。

下一最小代码单元应保留现有 capture（请求窗口、原始 receipt 时间、HTTP/字节/hash、RSS、绑定快照和预算），只隔离替换其 source-review 边界：给旧 baseline 与新 capture 分别绑定真实 basis、SID、split schedule、各自接收时间，用同一个现有 split normalizer 投影到同一当前单位，再逐日 Fraction 精确比较非空重叠；禁止用新 capture 自证 baseline。原 target/proposal 继续不改，另绑 transition 和当前 revision。只有 source review 全通过后，交本次 reader/风险库生成信号。

接线测试必须使用真实 capture_supplement 的受控 transport 返回、两代旧/新原始 receipt 和重复日期，覆盖 AS_TRADED/已复权两种、冲突重叠、少日、错误收件时间、未知 basis/行动和账户中途变化；不能只传新 full-window dict 就声称补采完成。本次仅定位，未新写补采代码或运行网络。


## 补采后续单元（隔离，尚未生产接线）

新增 `split_frontier_supplement_20261105.py` 和 `test_split_frontier_supplement_20261105.py`；既有 candidate reader 仅增加每 SID 接收时间映射，整体 received 必须等于各 SID 实际 received 最大值。

实际复用正式 gzip `capture_supplement`，测试使用真实 gzip.compress XML wire、Content-Encoding:gzip，由原 GzipRssTransport 解码和保存证据，网络禁止。完整固定 calendar 为 9/1–10/23，超过20会话；保留盘中、20会话窗口、monthly epoch、proposal/持仓/open order/peaks/exited 完整域。apply 从真实当前 risk、archive target/proposal 和 calendar 重算 current request 逐字段比较，另绑 proposal/risk hash。

旧 capture 10/21 在拆股前，按自身旧单位/接收时间归一，review 没有未来 split；再用现有 project_history_units 做明确后验计算投影，不改原始 bytes/receipt。新 capture 10/23 按自身 AS_TRADED 或已复权 basis 归一，最后共同单位精确比较非空完整旧窗口 overlap，并接已验 reader/risk。

SID 接收时刻刻意不同。daily 请求开始采用原 receipt 的 requested_through（原实现 before-fetch），核 observed_floor <= requested_through <= received <= finished；RSS started/received 单独核。120秒限制仅采集内跨度，没有新增 now-finished 硬TTL。action 从已认证准备 transition.action_id 精确唯一取得，且纳入外部可信 pair hash。

测试覆盖两 basis 完整链；重叠冲突、缺日、未知 basis/行动、接收时间错误、observed_floor 错误、捕获途中账户变化均拒绝。身份、价格、账户均合成，不能称真实供应商/券商验收。

边界：受控 capture→source review→reader/risk 隔离组合已实现；生产 SavedFrontierLiveReader 自动调用/配置尚未接入，独立供应商 basis 准入、三时钟分离、生产激活仍未完成。捕获成功不自动签发 basis 认证；本单元仍要求 server 所有者提供独立可信 review hash。

根线程独立验证：`D:/python/python.exe -m unittest discover -s tests -p test_split_frontier_supplement_20261105.py -q`，3项通过，32.125秒。原6路径综合测试此前3项通过，67.697秒；均为临时合成账户与受控来源，未操作真实账户。
