# 11月5日开盘前正式页面只读核验

北京时间19:50:13，使用现有 `capture_daily_ui_readonly_v1.cjs` 在隔离浏览器读取8010正式页面，所有非GET请求均被禁止，没有点击现金或成交按钮。

- 采集句柄86270终态exit0，当前建议WAIT，非GET请求0。
- `python -B -m scripts.review_daily_ui_capture_v7 tmp/readonly_premarket_ui_20261105_1951/capture.json` 复核为 `NOT_ACCEPTED_WAIT`，原因 `WAIT_POLICY_REVIEW_SESSION`，订单0。
- 实际四列表格与独立接口响应核对完成，财报日历1行匹配；账户采集前后相同。
- 这不是盘中有效买卖建议验收，也未验证现金按钮真实写入、AI有效风险意见或用户真实成交承接。线上V27和活动配置未修改。

私人原始页面、账户与截图仅保留在上述tmp目录，不提交GitHub。

拆股候选工作另行推进：工程可以提前准备，但未来券商到账与报价单位切换必须按真实事件核验；不能把未来证据缺失理解为当前未拆股链路已阻塞。
