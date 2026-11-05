# DTN2026-26 公告范围修复

真实 current 接口在现金确认后返回 WAIT_KNOWN_ACTION_REVIEW。保存的 RSS 中，MRNA/SNDK 均没有发行人匹配；唯一未来时间条目是 DTN2026-26，标记 2026-11-05 20:00Z，晚于实际采集时刻。

官方全文 https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-26 已读取：Daily List 迁移至 Data Link、API/SFTP、历史表及分发缓冲，计划2027年6月底前实施；没有发行人股份、CUSIP、现金或权益变更。保存原始 HTML SHA256 为 4515afd8865e7beba1d253d45b42265f6dfa018ab927cb0de5282651ebf578f4。私人运行证据仅留 tmp/service_recovery_20261106。

最小修复只增加精确类别、标题、摘要、链接匹配及已审阅正文证据。原始发布时间不修改；目标发行人匹配、截断、不同内容和频道未来时间仍拒绝。不是整个新闻类别豁免，也不宣称公司行动覆盖完整。

原始真实 RSS 对两只股票复核通过；4项新边界测试和2项原DTN25测试通过。第一次新测试误用了返回字段名，已修正。26层独立配置重建及引用hash核验通过。部署前后完整真实账户与月目标一致。

活动配置切换为 research_contracts/dtn26_20261106/config-25.json。生产策略仍V27，未制造成交或下单。启动及实际current建议仍需另行验证，不能把通过范围复核当成整条建议链通过。

## 部署后实际验证

新PID17460完成启动，首页HTTP200、账户READY；实际current GET返回daily.status=READY，绑定新现金确认revision和11月目标，已不再返回WAIT_KNOWN_ACTION_REVIEW。具体账户现金、持仓、挂单及接口原始证据只存本地；未创建订单。这是后端真实现金到建议验收，不代表浏览器整页、AI复核或用户成交承接通过。
