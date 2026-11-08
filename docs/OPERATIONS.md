# 使用与维护

## 日常操作

启动方法见[README](../README.md)。仅在8010未运行时启动；完整校验需要时间。现金输入是券商当前可用美元购买力，不能把未到账卖款或未成交委托释放额假定可用。录入真实成交后再核对购买力。

OPEN刷新可持续至收盘前5分钟，收盘退出阶段按原规则优先处理。OPEN目标和限价采用开盘参考，当前报价仍用于时效及资金等核验；延迟成交不是开盘回测成交。过期建议显示生成、到期和过期时长；同一标签页缓存只恢复参考，不恢复执行资格。图表是历史展示，不能代替报价。

## 月度维护

既有Windows任务：`UsRatchet-ROA-Monthly-Preparation` 与 `UsRatchet-ROA-Monthly-Handoff`。后者每15分钟检查，错开准备任务；依赖配置的用户登录会话。已有任务不要重复安装。

流程：月末完整数据 → 准备并校验月包 → 正式采用 → 运行配置读回 → 后继月计划与任务绑定。当前等待路径已实跑，真实未来月份闭环待验收。

- 准备状态：`scripts.inspect_roa_monthly_preparation`，使用任务Action中实际descriptor路径与SHA。
- 采用入口：`scripts.research.build_roa_monthly_adoption_request`，按当前部署请求和来源引用执行；不凭文档旧PID或旧哈希重启。
- 正式编排：`scripts.research.advance_roa_monthly_release`；运行确认及后继任务由其协调。
- 恢复：`scripts.prepare_roa_monthly_retry`默认只读预览；新尝试保留旧失败证据，不能覆盖未知结果后盲目重跑。
- 日历现覆盖至2027-02-01；需要继续补齐，不代表无限期自动运作。

中断后核对持久化意图、回执和当前版本，未知采用或重启结果先协调，不重复执行。任务退出0或WAIT只证明等待路径。真实页面、成交及新月目标仍需单独验收。

## 仓库边界

生产源码精简提交为`81a28ce8`：6752个跟踪文件减至948个，保留713个生产/维护绑定源文件；月度准备684路径依赖集合未变。后续文档整理另计，不改变运行源码。

旧名称模块因当前依赖保留，不表示启用旧策略。四份`docs/candidates/*.md`冻结合同参与来源校验，禁止随意改字节。`.gitattributes`禁止自动换行转换，避免Windows检出破坏固定哈希。

私有配置、真实账本、行情证据、研究原始数据及回滚包不上传。新克隆不能直接冒充当前实盘环境。历史内容仍在Git历史，不重写历史；不要在有未提交修改的生产目录执行强制reset/clean。

## 验证

```powershell
D:/python/python.exe -B scripts/verify_roa_portable.py
```

源码精简时验证通过：283项ROA便携测试、9项月度决策测试、10组前端测试及后端导入。便携入口排除三组依赖私有训练证据的测试；保留的部分旧辅助测试仍有接口断言问题，不能宣称全目录discover全部通过。文档改动不重新证明实盘或经济结果。

当前部署与待验收事项只看[验收清单](real_event_acceptance_checklist.md)及[TODO](../TODO.md)，旧研究合同的阶段描述不作当前状态依据。

## 成交更正与账户备份

成交价更正是独立追加日志，不能只备份主账户SQLite。使用以下命令生成新的本地账户备份目录（已有目录拒绝覆盖）：

```powershell
D:/python/python.exe -B -m scripts.backup_strategy_account --database E:/Git/us_ratchet/data/strategy_account/real_strategy.sqlite3 --output E:/Git/us_ratchet/tmp/account-backup-唯一时间戳
```

备份在短暂账户写锁下同时保存主账本及存在的`.fill_corrections.sqlite3`，校验SQLite完整性和重读投影一致后生成manifest。目录含私人账本，不上传GitHub。该入口不执行恢复，也不是整站备份：资金原因分类、绩效基线、生命周期、活动配置和任务引用仍需另行保存。恢复时不可遗漏更正文件，不能将账户备份误当作完整部署回滚。
