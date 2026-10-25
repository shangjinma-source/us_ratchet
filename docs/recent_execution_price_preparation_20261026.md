# 连续账本价格坐标准备（未授权经济执行）

新脚本 `scripts/prepare_recent_execution_prices.py` 只读全 36 月训练快照及其 `fixed_sources`，不联网、不选股、不 assemble、不改生产。范围 2020-12-31 至 2023-12-29。价格用精确 Fraction：从 calibration 日期/因子出发，向前经过坐标事件相乘、向后经过事件相除；事件当天采用变更后的坐标。只采用生产者最终 fixed_sources 事件表，原 Yahoo 事件不重新加入缩放。

实际快照 SHA `327b5e75da4f4d4d7eaf6bd79f58282b2f884b02053cd7b58fdc48940231fcb0`：124 证券、754 参考会话、3,600 个 READY 候选决策成本与对应恢复 close 精确相等。此快照仍有 CEG/GEHC/ON/TTD 四个 calibration 缺失，按异常保留，不填价；scope 更新后须重跑并绑定新 hash。

输出 `tmp/recent_execution_prices_20261026/execution_prices_v1.json`：

- `ohlc_by_ticker` 保留全部 124 标签，`ohlc` 仅含无身份冲突的 SID；FB/META 共用 SID 的合并交给明确 alias 规则，当前记录于 `security_identity_collisions`。
- `source_reviews` 列每票原来源/hash、实际边界、缺日/边界前后缺日/异常日期。不会从缺日擅自断言退市或未上市，不补价、不删成员。
- `provider_event_inventory` 含 SID、ticker、date、kind、provider_event、source/hash、是否在范围内及未准入标记。当前 1,383 事件含原流范围外事件；不能直接转成账本行动。
- `action_stream_missing` 为 SID 列表，`action_stream_missing_by_ticker` 提供 11 个 CSV 来源标签；无事件流不等于无公司行动。
- `runner_execution_authorized=false`。价格因子不生成股数变化，股息金额/税/支付日期均不自动映射。

所有输入先读取一次并绑定 hash，核对训练生产者绑定的源 hash，结束前再逐个核对文件未变化。若 scope 同步写入导致不同快照，明确失败而不输出混合版本；最后以临时文件替换方式写出。既有一月产物不修改。

测试覆盖普通拆股前后/事件当日、从早晚两个校准日反推同一结果、反向与复杂有理因子。使用 unittest discover；初次模块式调用因 tests 非包未找到模块，改 discovery 后运行，未触发经济搜索。实际 3,600 条精确决策价对照是额外数据接线检查，并非收益验证。

## 最终 36 READY 快照更新

scope 明确确认最终写完后重跑，训练 SHA256 `b120b6b0117d0b85ec4f393a5c6094713754ae55d4b8d683061b384a452db5f0`，执行价格输出 SHA256 `17b4e1287c6fb7e62f800e74fb76d9a3e6625d6f74e98c0047783f7c005eaf65`。36 窗口全部 READY、18 个合法排除、3,640 个 READY 候选决策价全部精确吻合。

新有效坐标表的 `apply_nominal_scale:false` 已显式尊重，增加拒绝错误 provider 因子的测试，共 3 项测试通过。MTCH 全 754 日恢复 close 与原 close 精确相等，未乘 3.502。

仅 GEHC 无校准；其六个成员出现窗口全部合法短史排除，标为不阻塞训练，但未来若经分拆权益等产生持仓仍必须取得名义 mark，不能静默估价。未删除 GEHC。两份旧 January 诊断 JSON 在本次重跑前后 SHA 未变。

独立检查 `final_snapshot_independent_checks.json` 保存上述计数、旧文件比较及 MTCH 检验。最终 hash 已发 github assembler；未运行经济搜索。
