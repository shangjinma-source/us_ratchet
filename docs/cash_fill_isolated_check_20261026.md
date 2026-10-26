# 现金及成交衔接隔离验证（2026-10-26）

本轮补齐现金按钮浏览器测试的 V27 提案绑定覆盖。未修改生产代码、真实账户或定时任务。

## 新增验证

`tests/test_cash_button_real_ledger_browser.py` 使用真实 Edge、实际前端脚本、账户 HTTP 路由及临时 SQLite。建议响应和行情为固定测试数据，不能证明实际选股、盘中报价或收益有效。

四个场景分别组合旧版/V27提案协议与结构化/非JSON服务错误，各自验证：

- 现金100覆盖为120，建议请求失败时已保存的现金保留，旧建议失效。
- 重试建议不再次写入现金；后续正常确认依然是余额覆盖。
- 再减少为50、减少为0，余额与建议使用同一账户版本。
- 页面完整刷新后余额仍为0，账户版本不变，没有新增现金事件或买单。
- V27请求携带提案编号，响应与月目标提案编号一致，并按提案风险目标接受响应。
- 持仓与订单不因现金确认发生变化。

四个浏览器用例全部通过。初次扩展时固定响应缺少V27必需的提案目标及风险目标，被前端正确拒绝；补齐测试响应后通过，没有放宽生产校验。

## 既有保护复核

16个Python用例通过，覆盖 `test_strategy_account_store`、`test_strategy_account_ledger_difference_integration`、`test_strategy_frontier_daily_route`：事务与去重、成交后现金重确认、版本冲突、提案绑定和异常响应不能暴露可执行订单。

前端 `strategy_account_reload_reconcile_mock.cjs` 与 `strategy_account_inflight_reload_mock.cjs` 通过：丢失响应或页面重建后沿用原成交事件ID核对，不以新ID重复录入；持久化失败时不发送成交请求。`strategy_daily_controller_mock.cjs` 的45个场景通过。

这些测试不代替用户下一笔真实成交验收，也不代替月底发布和新月目标衔接。原真实事件清单保持有效。生产仍为V27；本轮没有新的策略研究或收益结论。
