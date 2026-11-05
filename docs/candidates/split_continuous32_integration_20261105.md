# 拆股账户的原生选股、提案与日建议接通

未挂载候选复用原连续32搜索与结果验证函数，仅将输入和差额读取绑定到已有拆股实现；不修改经济算法、原模块全局变量或生产配置。原函数身份用LF规范源码哈希检查，部署输入的运行时哈希仍按原始字节校验。并未认证整个传递依赖闭包。

新增测试实际调用原enhanced_search（未mock搜索或建议），在临时拆股SQLite账户中生成正式REAL_STRATEGY_CONTINUOUS32_TARGET_DECISION_V1月目标，再用真实SavedFrontierProposalStore构建、保存并读回提案。合成输入得到原目标B26股、限仓提案B13股；日风险和差额采用13而不是26，行情解析和限价代码实际计算A卖16股及B买入建议。重放相同月目标请求保持同一结果；账户和原签名目标不变。

既有SplitRuntime新增显式frontier_view绑定，读取真实提案数量，并检查signal.proposal_id。错误提案ID在报价前拒绝，持久化提案被篡改后读取拒绝；未传frontier_view的既有基础链仍通过回归。

主线程独立执行两项测试均通过：

```powershell
D:/python/python.exe -m unittest discover -s tests -p test_split_continuous32_integration_20261105.py -q
D:/python/python.exe -m unittest discover -s tests -p test_split_runtime_integration_20261105.py -q
```

测试账户、行情、身份与历史信号证据均为合成夹具；结果保持CONDITIONAL_PREVIEW_READY。当前没有真实NewsInvestmentService完整任务成功、正式split-aware原始历史读取、生产路由切换或真实成交验收证据。下一步须完成这些接入，不得把条件状态直接改READY。真实未来拆股的来源、生效和券商到账仍须分别核验。
