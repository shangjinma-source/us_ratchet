# 当前四列表格与财报安排只读验收

新增纯DOM提取器capture_daily_ui_acceptance_v3.cjs，保留原四列和完整页面文本，单独采集财报日历节点。review_daily_ui_capture_v7.py核对实际原行及日历与独立GET上下文一致后，复用v6金融校验；不忽略未知AI意见、不以日历代替业绩判断。10项Python回归及Node DOM提取测试通过。

实际服务仍为8010进程42172、news_post_scope_20261104/config-29.json、交易策略V27。通过独立测试浏览器访问正式页面，未点击现金、未创建目标、未调用模型，所有非GET请求均阻止；实际观察到0个非GET请求。账户前后完全相同，当前11月目标/提案与页面一致，MRNA会议安排11/6 21:00（北京时间）与当次日历GET匹配。截图已目视，四列及等待说明可见。

复核结果为NOT_ACCEPTED_WAIT / WAIT_POLICY_REVIEW_SESSION：这证明休市页面与API的一致性，不证明盘中可执行建议、真实现金保存、AI经济效果、用户成交或图表全部完成。截图时图表仍显示读取状态，不作图表加载完成声明。新闻来源在截图时提示检查未完成，随后只读状态为两来源LIST_OK、NO_NEW_TIMELY_BODY、worker_alive=true且无worker错误；不能把一次等待当作永久故障，也不能把无新正文当作无风险。

复现入口（每次使用新的私人输出目录）：

```powershell
node scripts/capture_daily_ui_readonly_v1.cjs tmp/<new-private-directory>
D:/python/python.exe -m scripts.review_daily_ui_capture_v7 tmp/<new-private-directory>/capture.json
```

该入口只读，不替代正常现金按钮、AI复核及真实成交流程。使用本机既有Playwright/Edge依赖；不会控制用户已打开的浏览器标签页。私人证据在tmp/readonly_current_ui_20261104_2145，原截图与完整账户不上传Git。
