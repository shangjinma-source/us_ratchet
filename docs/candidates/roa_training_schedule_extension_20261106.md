# ROA 训练日期表延展（仅离线计划日期）

新增入口 `scripts/research/build_roa_training_schedule.py`，不改已发布日期表。默认生成 2025-01-01 至 2026-12-31，允许范围仅限已钉住 NYSE 官方 PDF 明示的 2024–2026 年。复用既有官方假日 review，逐项重核原文哈希；另核 runtime 日历、两层引用与扩展资料哈希，并要求重叠区间日期逐日相等。不是根据行情观测推定开市。

实际产物：`tmp/roa_training_schedule_through_20261231_20261106.json`

SHA256：`2e53ff8299638db2b435320c7f3595c9344a6f58c638a20297843ea22ce2d4d9`

共 501 个计划会话。与现 runtime 2026-09-22 至 12-31 共 71 个会话完全一致。现有 10-30 manifest 的最后 253 个训练日期保持一致；11-30 后下一会话为 12-01。12-24 保留（提前收市仍是交易日），12-25 排除，12-31 保留。

运行：

```powershell
D:/python/python.exe -m scripts.research.build_roa_training_schedule --output tmp/roa_training_schedule_through_20261231_20261106.json
D:/python/python.exe -m unittest discover -s tests -p test_roa_training_schedule.py
```

4 个测试通过：月界/早收市、Carter 特别休市、年份越界与 runtime 缺增日期拒绝、来源篡改与输出不可覆盖。旧文件与生产配置未变。

root另使用真实10月30日manifest和新日历运行正式月包准备dry-run，通过且十只选择与原版逐项一致。请求及结果保存在 `tmp/roa_calendar_extension_monthly_request_20261106.json`、`tmp/roa_calendar_extension_monthly_dryrun_20261106.json`，校验1253份来源、356030896字节；未创建复制包、注册月份或写账户。这证明新日期表与实际现有选股输入兼容，不证明未来12月输入已齐。

这是日期计划，不提供盘中时刻，不认证未来实际开市，不穷尽全部临时休市公告。仅补入已留证的 Carter 2025-01-09；后续若有临停须审核新增证据再发布新表。该产物可用于未来十二月月包的 training_calendar，真实 11 月末行情、财务可得性及月包尚未生成，不代表十二月换月已验收。
