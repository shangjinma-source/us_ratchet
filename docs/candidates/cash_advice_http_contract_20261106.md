# 候选 HTTP 编排与现有按钮契约

独立候选 router：`docs/candidates/cash_advice_router_20261106.py`，未被生产挂载。

- POST `/api/research-candidate/cash-save-and-preview`：仅 expected_revision、event；event仅event_id/kind/amount/cash_basis，kind须CASH_CONFIRM；正式accountservice继续验证值。
- POST `/api/research-candidate/advice-retry`：仅空对象，绝不写现金。
- POST `/api/research-candidate/cash-status`：与保存相同的原始body，只读查原event_id及完整payload。找到返回cash_saved=true；未观察到仍返回null，不能据此宣称请求未落账；同ID异payload拒绝。此端点不生成建议、不写账户。
- 两端禁止query、重复JSON字段、非有限JSON常量及超过8192字节。无weights/policy入口。
- 成功返回cash_saved/advice_ready/account_revision及嵌套advice中的已验证target_id/proposal_id；现金已保存但建议失败返回200和明确false，不返回旧建议；保存未知返回503/cash_saved=null。派发后未处理异常保守按保存未知，不依据异常类型断言未保存。
- 成功响应同时包含正式accountservice投影的account，与advice/account_revision一致。投影后重读账户，期间真实写入会使本次建议失效，不返回混合快照。隔离HTTP测试实际注入并发现金写入550并确认落账，同时验证旧建议未返回。

`tests/test_cash_advice_router_20261106.py`：1项真实TestClient组合测试通过，实际临时SQLite+正式accountservice+可信builder/provider。现金保存1000后报价失败，retry恢复买10且账本不变；重复event幂等、绑定IDs实际生成、JSON可序列化；客户端weights/错误事件/重复字段拒绝；注入保存未知返回503/null。建议依然executable=false，无生产操作。

## 现有前端最小接线位置（仅分析）

`web/strategy_daily_controller.js::createController` 接收saveCash/loadCurrentAdvice/loadTarget/generateTarget/previewDaily。现金提交路径当前先saveCash取得account对象及revision，再read(token,true,savedRevision)，必要时finishTargetRequest处理月份，最后走建议流程。`httpDependencies::saveCash` 调用accountController.confirmCash，不是组合端点；`web/strategy_account.js::confirmCash` 经mutate('/events')进行失效通知、版本处理与账户投影。

因此不能把组合响应原样替换saveCash：当前要求updated.revision，候选返回account_revision且没有账户投影；当前月目标展示/binding仍要求target_month等frontier字段，候选权重目标不是该schema。最小正式改动应在daily controller增加显式组合依赖及分支：保留account controller写前失效/写后读回投影，按cash_saved三态更新界面，advice失败只调用retry；成功采纳经过验证的同revision账户/目标/建议快照，不再额外生成旧月目标。HTTP依赖层选择专属新策略组合，不改变既有V27路径。

当前候选缺生产可采纳的完整前端target快照和经济准入。不能通过把研究false改true或伪造旧monthly字段强行复用页面。没有新页面、没有修改正式前端或已pin路由。

## 显式候选前端控制器

`roa_cash_controller_20261106.js` 提供save/refresh/accountInvalidated/getState；生产仍未挂载。集成方须注入账户隔离的持久pendingStore、expectedEpoch及请求/账户读取依赖。保存前保留完整原event，未知写入时拒绝新保存；刷新只读cash-status，确认原记录后仅advice-retry。账户失效通知使在途旧建议不能采纳，同步核对账户revision与策略epoch。不将候选response伪装成旧frontier目标。

Node场景验证实际请求顺序：网络中断→新金额保存被阻止→未观察到原记录继续等待→原记录确认→只重试建议；另验证在途账户失效及错误策略epoch不会显示建议。仍需正式mount、当前目标展示、执行时段与页面验收，不能将控制器测试称作已上线。

## 固定整股候选组合验证

roa_account_composition_20261106.py已将正式账户事件router、候选现金编排router及绑定建议router组合到同一个隔离账户库；强制提供固定target_quantities，不接受普通刷新重新配权的默认模式。组合本身未注册到生产mount，不启动服务，不修改真实库。

test_roa_account_composition_20261106.py实际TestClient验证：同一临时SQLite初始化→保存1000现金但报价失败→仅重试建议恢复9股目标→通过正式事件HTTP模拟买入4股→确认600现金后只建议剩余5股→重复提交同event幂等、账户未重复记账。此为合成交易，仅证明候选接口闭环；未验证真实页面、当前实际持仓迁移、策略盈利或用户真实成交。
