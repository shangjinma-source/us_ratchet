# Downside max10 v9：仅补最后21日账务，禁止新增搜索

父late_v8为625/646日、31份月选择均已计算、累计2550.014866100042秒。旧通用helper可验证八节点父链（seen深度0至7），无需修改安全深度限制；只输出第九代，不授权继续扩大链。

全部31份选择须完整arguments匹配；重放625日最新前缀通过后补余下21日会计。累计预算原10800秒/单月600秒不变。除原new31已触上限外，v9私有加载原v3模块，将实际select闭包查找的模块全局 `decide_observed_for_account` 替为无条件 `ACCOUNTING_ONLY_NO_NEW_SEARCH` 拒绝函数；任何意外cache miss都不能触发选股。原v3文件及其他进程不变。

新增仅GEHC7/24股息配对，freeze前原6/30父gate必须解除全部未映射事件。前序ordinary材料与INSM absence dispatcher不变，ASML事后Final应收估值限制继续适用。

测试核真实八代、31记录完整参数、625前缀；从真实v3 AST确认select调用该global，并通过真实run.__globals__解析执行拒绝stub，无经济运行。

根执行入口：`python -m scripts.research.run_downside_account_candidate_20261105_v9 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v8 --output tmp/downside_max10_20261105_late_v9`。待补证后freeze，准备期间不自动运行。
