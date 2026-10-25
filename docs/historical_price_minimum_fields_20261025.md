# 历史数据最低字段：训练与执行分开

已只读复核实际入口，没有降低 schema 或改动生产。

`backtest/return_priority_monthly_training_inputs.py` 的 `compile_monthly_training_window` 需要 **253 个合法正数 close**、对应递增会话和一个 `decision_cost`，不读 open/high/low。其 12 个训练场景由每隔 21 个会话的 close 比值计算；接口仍严格要求全部 253 个 close，不能因数学上只取若干点而缩减输入。执行组装器要求 `decision_cost` 等于决策日的执行 close，单位必须一致。

`backtest/return_priority_monthly_execution_inputs.py` 组装层只读取 close；`v4` 增加日期化来源/分拆接续，并不自行验证全 OHLC。但真正调用的 `historical_dividend_next_open_book_research.py:331` 对持仓或活动订单先读取并校验 **open/high/low/close 全部四项**。成交计算用 open，收盘持仓及权益估值用 close；high/low 在该 next-open 版本中承担输入合法性校验，当前接口仍不可省。原限价模型 `return_priority_limit_book_v2.py:196` 还直接用 high/low 判触价，因此不能把仅开收盘数据推广到限价模型。

以下初始缺口表记录加入本轮新来源前的 V4 域；不代表最新缺口。按该域重算各字段的缺失日期，输出 `monthly_price_routes_v5_fields.json`。逐行新增 `training_close_missing`、`execution_open_close_missing` 和各字段单源/union覆盖；`execution_full_ohlc_schema_still_required=true`。现存数据的字段放宽诊断没有凭空增加齐备月份，仍为 10 个训练日期层完整月。

**下列纯训练缺口，可优先使用合格 close-only 原始来源解决，不要求补开高低：**

| 证券 | 纯训练缺口 | 会话数 |
|---|---|---:|
| CERN | 2020-01-02—2020-12-31 | 253 |
| MXIM | 2020-01-02—2020-08-24 | 163 |
| XLNX | 2020-01-02—2020-12-31 | 253 |
| WBD | 2021-12-30—2022-12-30 | 253 |

WBD 的历史身份/分拆与前身映射仍未核，这不是允许拿另一家证券的 close 拼接。close-only 源仍须明确证券、日期、价格单位和固定来源优先级；不使用 adjusted close 冒充现有训练坐标。

**下列缺口同时承担执行，close-only 不能完成当前 runner 输入：** CERN 2021-01-04—06-04（106 日）、XLNX 2021-01-04—02-10（27 日）、SGEN 2022-12-12（1 日）、SPLK 2022-12-12—12-30（14 日）、WBA 2022-12-12—2023-12-29（264 日）、WBD 2023-01-03—12-29（250 日）。至少需 open/close 支持成交估值，且当前 kernel 仍要求真实 high/low 完整校验；不制造 high/low 填洞。并购后旧股已退出报价义务，转换与所得权益估值要求另外保留。

复用原脚本生成字段诊断，无新增框架：

```powershell
D:\python\python.exe -m scripts.audit_recent_monthly_price_routes_v3
```

V4 文件未覆盖；当前脚本输出字段版 V5。仅集合覆盖诊断，未运行收益或选股搜索。

## 10月26日集成更新

同一脚本已纳入经复核的MXIM/XLNX候选、CERN两段原始行情、SPLK/SGEN公开表和WBA Zenodo整段行情。训练日期层完整月份为2022年1—12月；其余窗口的当前缺口为CERN 2020-08-03—12-16（96日）、XLNX 2020-08-03—08-25（17日）、WBD接续训练253日和2023执行250日。上述原始表仍需固定来源组合与单位/权益准入，日期并集齐备不等于正式回测输入。WBD的DISCA→WBD一比一接续已另有原始文件证据，异常周末记录的WISEPLAT候选未接入。
