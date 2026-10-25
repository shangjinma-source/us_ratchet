# SPLK / SGEN 归档尾日及短缺口：真实 OHLC 候选

本批使用两条公开路线，未运行经济搜索。ChartExchange 页面实取成功；FinanceCharts 三票各一次请求 HTTP 403，立即停止该来源，未重试或绕过。WBA 本批没有新增有效行情。

## 有效证据

来源：<https://chartexchange.com/symbol/nasdaq-splk/historical/> 与 <https://chartexchange.com/symbol/nasdaq-sgen/historical/>，各 HTTP 200、370 行。原始 HTML SHA 和 URL 保存在 `tmp/splk_sgen_bridge_20261025/manifest.json`。

| 目标 | 取得原 OHLC | 日历检查 | 既有归档重叠 | Quiver 重叠 |
|---|---:|---|---|---|
| SPLK 2022-12-12 至 12-30 | 14 日 | 14/14，无多余/缺失 | 55 日，54 日一致，仅 12/12 高价/收盘不同 | 252 日全部一致 |
| SGEN 2022-12-12 | 1 日 | 1/1 | 118 日，117 日一致，仅 12/12 收盘不同 | 252 日全部一致 |

OHLC 一致阈值为 0.011 美元；日历参考已保存 AAPL Yahoo 时间戳，而非独立交易所日历。目标 OHLC 全部为正并满足低高价包含开收盘。

2022-12-12 实际读数：

| 证券 | Open | High | Low | Close |
|---|---:|---:|---:|---:|
| SPLK | 87.42 | 92.19 | 87.37 | 92.16 |
| SGEN | 124.85 | 132.58 | 124.83 | 131.84 |

旧归档末日 SPLK High 比本源少 0.94、Close 少约 1.10000244；SGEN Close 少约 1.11499390。符合此前“旧归档末日可能为盘中快照”的疑点，但不能把推测写成供应商确认。旧行完整保留，不静默覆盖。

## 使用边界

交付 `SPLK_target_patch.csv` 与 `SGEN_target_patch.csv` 为有来源的真实候选，不是伪造或插值。两源长重叠为价格单位与常规日期提供支持；目标 12/12 本身仍只有本次成功取得的一个新来源，FinanceCharts 搜索摘要不能冒充完整页面核验。

建议将已发布历史日表优先于旧归档最后一天的规则作为显式来源优先级，并记录审批后再并入输入；规则应由来源覆盖/日线完整性确定，不能按回测收益择价。完整 ChartExchange SPLK 页面还覆盖 2023 年早段，可供主线程统一来源时使用，不必只截这 14 日。

全部原始 HTML/CSV、`overlap_audit.json`、`calendar_audit.json`、403 响应证据留在上述 tmp 目录。不宣称已进入主账、通过公司行动审计或完成策略回测；未修改生产。
