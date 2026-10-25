# 2021—2023缺口行情有界核查

机器核对11标签：ALXN、ANSS、ATVI、CERN、EA、MXIM、SGEN、SPLK、WBA、WBD、XLNX。此前口头清单漏ALXN且误把2020额外项写成ALXN；实际2020额外项为CTXS，区间报告已由机器清单纠正。

每标签最多一条本轮不同路线。EA/WBD改用Yahoo公开chart的range=max（此前是明确period起止），实际均HTTP429；停止，不重试，不将限流解释为没有行情。

其余9标签各查询一次Quiver公开历史页面，HTTP200，保存完整原始HTML、哈希及表格CSV：

| 标签 | 表格行数 | 首日 | 末日 |
|---|---:|---|---|
| ALXN | 253 | 2020-07-20 | 2021-07-20 |
| ANSS | 251 | 2024-07-16 | 2025-07-16 |
| ATVI | 252 | 2022-10-12 | 2023-10-12 |
| CERN | 254 | 2021-06-07 | 2022-06-07 |
| MXIM | 253 | 2020-08-25 | 2021-08-25 |
| SGEN | 252 | 2022-12-13 | 2023-12-13 |
| SPLK | 252 | 2023-03-16 | 2024-03-15 |
| WBA | 251 | 2024-08-27 | 2025-08-27 |
| XLNX | 254 | 2021-02-11 | 2022-02-11 |

来源形式：https://www.quiverquant.com/stock/ATVI/historical-prices/ （替换标签即各固定URL）。表格明确是最后12个月；全文价格图显示Premium锁定、原始数据按钮导向API，不尝试绕过付费限制。没有购买或注册。

字段为Date/Open/High/Low/Close/Adj.Close/Volume。日期单元格附股息说明，解析须把日期与说明分开，否则会错误丢失除息日。已保留9条股息注释：ATVI1、CERN4、MXIM1、WBA1、XLNX2；支付日期未知。可见Close与Adj.Close不同，但尚未认证原价/拆股单位，不能径直接名义账。

本轮取得9份部分实物行情，不等于填齐9个完整缺口。所有11标签仍未获完整预热+存续期准入。原始证据位于 `tmp/modern_missing_probe_20261025/manifest.json` 与 `quiver_manifest.json`；含完整来源、原字节SHA、范围、事件注释，admitted=false。未跑经济回测、未删缺失股。
