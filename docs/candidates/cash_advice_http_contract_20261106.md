# 候选 HTTP 编排与现有按钮契约

独立候选 router：`docs/candidates/cash_advice_router_20261106.py`，未被生产挂载。

- POST `/api/research-candidate/cash-save-and-preview`：仅 expected_revision、event；event仅event_id/kind/amount/cash_basis，kind须CASH_CONFIRM；正式accountservice继续验证值。
- POST `/api/research-candidate/advice-retry`：仅空对象，绝不写现金。
- 两端禁止query、重复JSON字段、非有限JSON常量及超过8192字节。无weights/policy入口。
- 成功返回cash_saved/advice_ready/account_revision及嵌套advice中的已验证target_id/proposal_id；现金已保存但建议失败返回200和明确false，不返回旧建议；保存未知返回503/cash_saved=null。派发后未处理异常保守按保存未知，不依据异常类型断言未保存。

`tests/test_cash_advice_router_20261106.py`：1项真实TestClient组合测试通过，实际临时SQLite+正式accountservice+可信builder/provider。现金保存1000后报价失败，retry恢复买10且账本不变；重复event幂等、绑定IDs实际生成、JSON可序列化；客户端weights/错误事件/重复字段拒绝；注入保存未知返回503/null。建议依然executable=false，无生产操作。

## 现有前端最小接线位置（仅分析）

`web/strategy_daily_controller.js::createController` 接收saveCash/loadCurrentAdvice/loadTarget/generateTarget/previewDaily。现金提交路径当前先saveCash取得account对象及revision，再read(token,true,savedRevision)，必要时finishTargetRequest处理月份，最后走建议流程。`httpDependencies::saveCash` 调用accountController.confirmCash，不是组合端点；`web/strategy_account.js::confirmCash` 经mutate('/events')进行失效通知、版本处理与账户投影。

因此不能把组合响应原样替换saveCash：当前要求updated.revision，候选返回account_revision且没有账户投影；当前月目标展示/binding仍要求target_month等frontier字段，候选权重目标不是该schema。最小正式改动应在daily controller增加显式组合依赖及分支：保留account controller写前失效/写后读回投影，按cash_saved三态更新界面，advice失败只调用retry；成功采纳经过验证的同revision账户/目标/建议快照，不再额外生成旧月目标。HTTP依赖层选择专属新策略组合，不改变既有V27路径。

当前候选缺生产可采纳的完整前端target快照和经济准入。不能通过把研究false改true或伪造旧monthly字段强行复用页面。没有新页面、没有修改正式前端或已pin路由。
