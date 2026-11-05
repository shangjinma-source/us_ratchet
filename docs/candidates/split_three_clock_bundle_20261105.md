# 三时点账户与风险准备包

原`data/strategy_split_bundle_v1.py`依赖单时点投影，不能直接作为三时点候选的发布包。本隔离实现保留原账户迁移、独立风险SQLite、失败痕迹、完整manifest发布及原源revision复查；改用已验证的三时点native/history/risk投影。

timing及固定日历进入inputs、transition和风险archive，manifest使用独立`SPLIT_THREE_CLOCK_PREPARATION_BUNDLE_V1`。准备前校验当前已到Q/B/C/K；验证时重放账户、历史峰值、退出状态、价格存档和准备记录。仅重新计算文件hash不足以替换时点并复用旧transition。

`D:/python/python.exe -m unittest discover -s tests -p test_split_three_clock_bundle_20261105.py -q`：3项0.159秒通过，覆盖隔夜发股/次日报价/稍后实际可交易的双库完整重放、原库字节不变、重哈希时点篡改拒绝，以及未来凭证不创建准备目录。

仍为临时合成账户验证、未部署。此包不等于真实券商证据认证、全运行时原子切换或旧进程退役。

后续接入`bound_split_sources`：私有绑定原三库锁定逻辑与新三时点完整验证器，持锁内核对原账户revision、目标、风险和manifest。4项最终测试0.251秒通过，包括三库写入受阻、退出后释放，以及准备后真实现金事件使旧准备包失效。作用域只供本地切换，不允许网络或模型工作；仍没有自动激活生产。
