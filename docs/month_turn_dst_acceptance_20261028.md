# 月底、新月与夏令时验收时间（2026-10-28只读核验）

以下均为北京时间，依据生产已绑定交易日历及当前Windows任务登记；不是未来数据或目标已验收。

| 事件 | 正确时点 | 当前实际限制 |
|---|---|---|
| 10月30日美股开盘 | 10月30日21:30 | 仍为夏令时 |
| 10月最后交易日收盘 | **10月31日04:00** | 此后才可取得10月30日完整收盘数据；月末选股验收不能在10月30日白天完成 |
| 11月2日新月开盘 | **11月2日22:30** | 11月1日已结束夏令时；此前21:30承诺须纠正 |
| 新月首次审核允许开始 | **11月2日23:00起** | 原代码明确要求开盘后30分钟；15分钟任务当前相位约23:14首次符合。只是开始机会，不保证目标立刻READY |
| 11月2日美股收盘 | 11月3日05:00 | 06:15建议后续观察任务仍在收盘后 |

生产日历与月任务boundary分别明确10/30 close20:00UTC、11/2 open14:30UTC。月任务`UsRatchet-RealMonthly-Update`每15分钟持续轮询，开启StartWhenAvailable，当前launcher全部源码pin匹配；不需要因DST改它，更不能为赶22:30而移除原open+30min门槛。21:10日源任务预取前20个已收盘会话，不因尚未开盘自动跳过。纸账户每日22:00和23:00两个触发分别覆盖夏/冬10:00ET决定窗；其窗口仅1分钟，主机延迟仍可能漏过。

全部相关任务为Interactive登录；电脑注销、睡眠或任务迟启会影响执行。StartWhenAvailable不能保证赶上窄窗口。验收安排应更新到上述时间，并查看真实运行结果，不修改现有金融任务。官方规则与本地日历一致：[NIST夏令时规则](https://www.nist.gov/pml/time-and-frequency-division/popular-links/daylight-saving-time-dst)、[Nasdaq交易时间和假期](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule)。

早先06:15任务10/28返回2，确实曾有14条到期观察因历史来源重审阻塞。此问题已于10/28 18:38的有界恢复运行解决：14条发布并回读通过，原117条完整性重验通过，共131条；3次来源请求，账户未改变。历史审核使用原代码及原时点，未修改旧pin。Windows任务“最近退出码2”仍是早先计划运行的记录，不代表恢复运行失败。

本地可核验快照：`tmp/month_turn_dst_audit_20261028/`的`tasks.json`、`audit.json`、`followup_diagnosis.json`。日历pin为`1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af`；当前任务登记只是本次读取快照，后续变更需重新核验。

2026-10-29凌晨在R35上线后再次只读预检：建议跟踪131条已完成、436条未到观察收盘，0到期积压、0阻塞、0网络请求；月度正式launcher按任务登记的配置与哈希通过，返回WAITING_SESSION_CLOSE，account_writes=false、target_created=false、http_calls=0。未重复执行采集或修改定时任务。证据：`tmp/goal_acceptance_audit_20261029/`；历史恢复独立回读见`tmp/followup_historical_review_20261028/recovery_independent_acceptance.json`。这些结果不替代真实成交、月底发布及新月采用验收。
