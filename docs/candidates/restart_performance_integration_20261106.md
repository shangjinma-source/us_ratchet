# 重新起算绩效：完整候选接入

非生产活跃实现已准备：`data/strategy_restart_performance.py`、`api/strategy_restart_performance.py`。正式模块无docs.candidates导入。候选完整账户前端为`strategy_account_restart_performance_20261106.js`，替换目标是web/strategy_account.js，但本轮未替换活跃源。

服务端调用`build_router(root=...,configuration=...,read_account=可信完整账本读取,valuation=正式估值服务,clock=...)`，并include_router。配置只接受固定schema以及baseline/ledger路径SHA；路径限于data/strategy_account/performance_baselines，拒绝父目录、链接和越界。每次读取原字节核对SHA。私有配置已生成于该ignored目录的router_config_20261106.json，不提交账户文件。

当前估值前后完整账户revision必须一致，当前估值时间最多120秒且不得未来。旧初始估值可历史保存。未知现金流不认证收益；原始账本无任何写入。接口仅GET，拒query。返回起始资产、当前资产、本阶段收益、估值时间；单快照不提供最大回撤结论。

账户栏在既有估值刷新后读取新接口，单行显示起始/当前资产与本阶段收益；无新增按钮。接口失败、过期或账户版本不符显示待核验，不影响已成功现金/成交写入。页面不把成本金额当当前阶段市值。

验证：正式模块API隔离测试通过；前端语法检查通过，4项渲染校验覆盖有效收益、版本不符、过期、缺失。尚未生产挂载，未完成真实页面端到端验收。需要发布agent纳入data/api源pin及候选web哈希，使用现有正式估值依赖完成构建和回滚，随后才可宣称上线。

## 实际V33构建与HTTP验证完成

在私有隔离stage复制实际配置引用及独立SQLite备份，保持生产源和active manifest不变。实际mount_strategy_routes构建UNIFIED_V33完成（约204秒）；真实正式估值依赖经候选API返回200 READY_RECONCILED_NO_EXTERNAL_FLOW，POST405、携客户端路径query409。单快照maximum_drawdown_fraction为null，未伪称连续回撤。全部过程约231秒，证据仅本地tmp/restart_performance_deployment_20261106/build_http_result.json。

候选入口research_contracts/restart_performance_20261106/config-26.json，SHA256为4262365e369e09c2020aa75e18a1bf6fbee9269a530b90753c850f78bcbd3862。基于news_context_dedup_20261106配置；web账户脚本首次由V33明确pin，mount源在旧层同步重绑。改动与回滚字节、next/previous active均在上述私有部署目录。当前可进入主线程部署审查，仍未激活生产或验收真实页面。

追加验证：纯计算测试已改为直接导入正式 `data.strategy_restart_performance`，2项测试通过。正式API测试增加成交后读取：初始1000、买入2股各100并扣1费用、现金799、市值220，接口收益为19/1000，且完整账本读前读后不变。该隔离测试通过，但不替代用户真实成交验收，也不代表未分类入金已经支持收益认证。

## 生产部署与页面失败，2026-11-06

完整隔离构建及正式估值依赖验证通过后，已部署 V33 工程接入，服务 PID 21744；账户与月目标完整前后比对一致。经济策略仍为 V27。部署证据位于 `tmp/restart_performance_deployment_20261106/`。

真实只读页面验收未通过：`tmp/verify_restart_performance_ui_20261106.cjs` 等待绩效展示240秒超时。后台估值曾返回200，但页面未完成绩效展示。已定位前端定时账户load在同revision时也递增generation并替换model，导致长估值结果丢弃；同一load还会清除已有绩效。修复候选正在独立测试，尚未部署。不能把服务启动或隔离API成功称为页面验收成功。

## 同版本轮询竞态修复已部署

四组正式前端控制器测试通过：同版本轮询保留在途估值、账户变更/失败/写入/dispose拒绝旧结果、按估值版本合并请求且旧请求不清新请求、所有WAIT/EMPTY清除旧绩效。完整候选与实际部署文件SHA一致。新服务PID39112已启动，账户与月目标完整比对一致，证据`tmp/account_poll_safe_deployment_20261106/`。实际只读页面复验正在进行，不能提前声明通过。V27经济策略未改。
