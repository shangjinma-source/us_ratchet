# 独立拆股月度 release → rolling router 接线

本轮完成隔离真实跨月选择链，未激活生产：原发布资料及源码pins→新独立ready envelope→完整源/单位重放→profiled release CAS→真实rolling operation snapshot→原continuous32搜索→target SQLite→原SavedFrontierMonthlyView proposal。

新增代码：`split_profiled_monthly_20261105.py`、`split_monthly_ready_verifier_20261105.py`。后者为原ready verifier的静态最小派生，仅将已有虚拟source路径`split-monthly-training-review.json`映射到本outer明确hash绑定的每月独立review路径；不覆盖root固定文件，不改旧receipt。新增单元测试`tests/test_split_profiled_monthly_20261105.py`。

## 验证

最终同版 session26889：2综合测试 PASS，48.023秒。命令 `D:/python/python.exe -m unittest test_split_profiled_monthly_20261105 -v`（PYTHONPATH=.;tests）。

1. 使用真实原publisher产生的合成资料，两个月独立不可变source namespace/registry/archive，真实A持仓2股经已记录split变16股后贯穿两月；分别执行INITIAL和MONTHLY_SELECTION、真实连续32搜索及target/proposal持久化。两ready采用CAS并支持幂等；两次target请求幂等。原12情景/选择参数未改。
2. 追加现金后直接把旧ready用于当前revision校验会拒绝；已采用release的snapshot继续按历史revision前缀重放，合法后续账户变化不让历史证据失效。
3. 独立旧语义测试使用原prepare与原adopt，真实prepare_split_account复制迁移临时库，追加split及现金，再由新LegacyPrefixActivation重放原ready的拆前账本前缀；原receipt bytes不变，实际split后股数为2（拆前1）。

两个月实际生成目标/proposal及对应账户快照已存本地：
`tmp/split_profiled_monthly_704f91c09be44adea73cdbc3fd4ebd35/december-target-proposal.json`
`tmp/split_profiled_monthly_704f91c09be44adea73cdbc3fd4ebd35/january-target-proposal.json`
都是合成非真实账户。测试临时源树随后清理，这两文件用于检查新目标绑定，不冒称可单独重放完整源链。

## 安全与剩余边界

新ready外层明确`SPLIT_PROFILED_READY_CONTENT_V1`，引用完整profiled ready body及`SPLIT_MONTHLY_EXECUTION_APPROVAL_V1`。批准绑定完整configuration hash、独立history review hash、timing及本轮全部实际router/ready/activation代码闭包；每个源同时核配置hash、文件bytes和执行源码。保留原archive history preservation/CAS/account-before-target锁/二次验证。

旧target缺新approval时仅允许按原archive构造旧runtime用于历史读取，不允许拿它生成新的split-era目标；新generation必须命中独立approval。旧runtime的遗留valuation/preview不据此宣称已支持拆股，它们仍需根线程统一daily/runtime组合。

本轮测试的两个月日期和交易日历是受控合成日期（包含人为月界），不能当真实元旦/交易所日历认证。跨训练窗口的原始/已复权价格精确核对由上一factory测试覆盖，本轮实际held split为训练域之外持仓；两组互补，未伪称真实供应商月度资料全部认证。

新月daily signal必须绑定新target/proposal及完整当期单位，不能重用旧split preparation的target quantities。根线程已针对该边界增加拒绝和真实monthly risk reset验证；本模块不生成daily signal，也不替代该接线。

生产激活仍需成组generation切换、旧进程退出与新进程单例启动；仅改active文件不能证明旧进程已停止。不修改真实账户、线上服务、定时任务或既有冻结研究文件。
