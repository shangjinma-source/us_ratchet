# ChartExchange 三票有界核查

本批 CERN/WBA/WBD 各一次公开 historical 页面请求，全部 HTTP 200；未登录、未绕 Premium、未探额外分页/接口、未做经济搜索。

| 公开页面 | 实际表格行数 | 最早 | 最晚 | 能否补目标缺口 |
|---|---:|---|---|---|
| https://chartexchange.com/symbol/nasdaq-cern/historical/ | 370 | 2020-12-17 | 2022-06-07 | 增加 2021 年早段，但 2020 预热仍缺 243 个会话 |
| https://chartexchange.com/symbol/nasdaq-wba/historical/ | 370 | 2024-03-07 | 2025-08-27 | 不覆盖 2023 |
| https://chartexchange.com/symbol/nasdaq-wbd/historical/ | 370 | 2025-04-15 | 2026-10-05 | 不覆盖 2023 |

字段为 Date/Open/High/Low/Close/Change/Volume/Change Since。CERN 和已保存 Quiver 日线重叠的逐日 OHLC 比较保存在 `CERN_overlap_audit.json`，容差 0.011 美元；原始两源均保留，不自动拼接。预热缺口使用已保存 AAPL 时间戳会话集计数，不声称独立交易所日历认证。

这条公开页面路线不能单独补全 CERN 253 日预热，也不能解决 WBA/WBD 2023 缺口。本批停止；不把页面未覆盖或供应商空白解释为证券停市。CERN 新增部分可保留为后续来源候选，尚非完整输入。

证据全部在 `tmp/chartexchange_three_probe_20261025/`：三份原始 HTML 及 SHA256 `manifest.json`、三份提取 CSV、`table_audit.json`、`CERN_overlap_audit.json`。未发布原始数据、未改生产。
