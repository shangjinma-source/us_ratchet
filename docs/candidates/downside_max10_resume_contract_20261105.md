# Max10 后窗固定续接 v2：执行前合同

本次只恢复 `tmp/downside_max10_20261105_late_v1`，不改v1冻结源码，不干预早窗。父后窗为BLOCKED，已完成21/646日，2次新搜索，累计149.63515230000485秒。新输出必须独立目录；没有自动重试。

- 从父contract/summary/book及2023-12-29、2024-01-31两月selection+sidecar读取版本JSON；核父全部source pins及各父工件hash。两月动态账户完整arguments（现金、股数、revision、quotes、search arguments及来源）逐字段相等才复用；不能按日期或目标相同复用。
- 父搜索new=2计数及elapsed完整继承；复用记录另计replayed不减new。剩余总窗预算10800秒与31次new不重置；新月仍600秒和8192/32、最多10只、cap50、原20%退出。
- 父sidecar以父已核research pins验证，不事后换成v2pins重签；新月sidecar绑定v2来源。父候选domain/选择及金融规则不变，新增META证据仅影响准确已证公司行动gate与配对实际账本事件。
- META artifact需精确ticker/SID、ex=2024-02-21、payment=2024-03-26、nominal0.5 USD、0研究预扣、全部provider observations、官方证据及hash。当前只是接口期望，**没有官方支付证据或新freeze则不得执行**。实际补证若不一致须拒绝并报告，不硬凑。
- 新freeze schema `DOWNSIDE_MAX10_RESUME_EXECUTION_V2`，包含v2 runner、续接helper、META artifact/资料与其余完整依赖闭包。v1 freeze原封保留；新旧源冲突fail。freeze状态READY仅技术可执行。
- 重放结束（完整或再次BLOCKED）须核父21日日账本前缀逐字段一致；不足21日、任一字段改变都失败，并保存newbook供审。父工件结束再核hash。

现3项续接前提测试通过：真实父两月/预算读取、完整参数偏差拒绝、账本前缀改动/截断拒绝。尚未执行v2经济续跑，META补证及完整freeze待根统一复核。用户已授权研究，阻断是技术证据要求。

最新补证与早核验：META artifact已覆盖10笔（2/21/24至6/15/26除息，末笔实际付款6/25/26），接口逐条精确provider/SID/金额/付款核验，artifact hash3781f42104301307194fa91d82a9db9696f0c1e2a5d7c2f47ca240c438492413。provider原有state.daily_ledger允许逐日核已重放父前缀，满21日之前禁止任何新搜索；parent_prefix_boundary保存首次完整边界证据，不必跑完整窗才发现错误。仅后窗准入，父20k/0费5bp以及固定Jan31行动阻断原因均检查。
