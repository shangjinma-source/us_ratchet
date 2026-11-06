# SMCI 已有拆股身份与价格链复用核对

本轮只读本地资料，无下载、回测、生产修改。问题是后窗诊断 2024-09-30 缺旧 SID；已有执行输入确实含该日旧 SID，不能通过猜 ticker 别名修补。

- 旧 SID：`security:0001375365:86800U104`。
- 新 SID：`security:0001375365:86800U302`。
- 比例：1 旧股换 10 新股。
- 法律生效：2024-09-30 17:00 America/New_York；新交易单位：2024-10-01。9/30 日内及收盘仍是旧身份/旧股单位。
- 官方来源已存于 `tmp/old_window_exposed_actions_20261026_v1/smci_split_review_v2.json`：NasdaqTrader ECA2024-451、旧身份 SEC 文件及发行人材料。其 11 项 source_hashes 本轮全部重新匹配。原文标记是身份事实审查，不是生产交易授权。

## 准确读取入口

`tmp/momentum_split_mapping_20261105/mapping.json` 的 SMCI record 给出精确 split_identity、原 provider 10:1 观察和 8 项跨日 OHLC 单位检查；SHA256 `6dc917e61e9b2d74e0e104659f3f9627800a6a79d24c631215d05f0900d0f1f0`。

`tmp/old_continuous_baseline_20261026_v9/execution_inputs.json` SHA256 `b777b58c23b1f36ee30463e926c170e1983b844b96b8e2a2cb27b6b4f11d2672`：

- `ohlc[old_sid]` 覆盖 2023-12-29→2024-09-30，9/30 close=`1040999984741211/2500000000000`（约 416.40）。
- `ohlc[new_sid]` 覆盖 2024-10-01→2026-07-30，10/1 open=`167/4`（41.75）。
- `assembled.actions` 和 `assembled.provider_actions` 已有上述配对 split_identity。`FixedSplitAdmission.install` 对该已有事件要求原样存在，不负责补造。

原 OHLC 源为 `tmp/fixed12_extended_quote_capture_20261014_v1/SMCI.response.bin`，SHA256 `de16278803b800a8b9d393e5b8cb848566a876da8537fae21a141edce1e5ad6a`。提供商返回拆股后坐标；已有执行输入恢复拆股前价格×10、拆股后×1。不要对已恢复执行价重复复权。

## 训练与连续价格约束

`tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json` SHA256 `32d7293282553d4c98daa161641663c0082da8f85b8b638974863f1ea8e951d3`：9/30 window 的 SMCI candidate 是旧 SID，training_dates 为 2023-09-28→2024-09-30；10/31 window 改为新 SID。training_close 来自同一原始来源的拆股后坐标，收益比例不应再乘拆股。该候选身份仍包含 retrospective 标记，不能说已证明全 PIT。

固定原旧股单位的持股价值链可以用 9/30 以前旧名义价格，10/1 起使用新名义价格×10；等价账户撮合方式是在生效点把数量×10、单股成本/止损/ATR÷10。两种表示必须择一保持一致，不能重复转换。跨身份的训练与持仓需要精确事件绑定，不能只因发行人/ticker 相同接续。

若诊断在 9/30 找不到旧 SID，应先对照其实际读取文档与索引：上述已存在 9/30 旧身份价格，10/1 才迁移。没有据此扩大其他日期或证券的准入；公司行动完整性、当时可得性和实际经济验收仍受原文限制。
