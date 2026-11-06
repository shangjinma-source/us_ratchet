# 残差候选九项既有分红资料复用独审

范围严格限既有匹配九事件及其明确引用文件，无下载、全目录扫描或回测，无准入变更。

只读索引：`tmp/residual_nine_reuse_independent_20261106.json`。原索引空的`local_source_checks`并非无证据：账户产物采用exact JSON的`payload/source_hashes`顶层绑定。已解码并逐文件核对九项代表产物的顶层来源hash，全部相符；hash相符仅证明文件未变，不自动证明整理笔记等于原始公告。

## 可进入隔离复用检查的四项（仍需精确绑定）

| 事件除息日 | 名义现金/支付日 | 已核来源及复用条件 |
|---|---|---|
| XEL 2021-06-14 | USD .4575；2021-07-20 | `tmp/rsi2_xel_review_20261106/review_rows.json`绑定发行人页面、widget和官方feed；feed给出普通现金、除息6/14、登记6/15、支付7/20。四来源hash全符。原row同时精确记录provider .458及原来源hash，因此可复用这一个精确舍入见证；不是允许所有金额误差.0005，账本用183/400。 |
| MSFT 2025-08-21 | USD .83；2025-09-11 | `tmp/rsi2_msft_intu_intc_review_20261106/MSFT_2025-08-21_observation.json`嵌套指向发行人年报HTML，原文字节hash核对通过。现候选使用10/14capture，原row为10/13，必须对新capture事件timestamp/amount和source hash重新绑定。 |
| NXPI 2025-09-17 | USD 1.014；2025-10-08 | `tmp/rsi2_adi_nxpi_review_20261106/review_rows.json`及NXPI_2025.raw hash通过。普通股，不是ADR换算。原声明明确荷兰15%预扣税，旧账本gross零预扣是研究假设；不得宣称真实净到账。新10/14capture须与旧10/13见证逐字段匹配。 |
| LIN 2026-03-11 | USD 1.60；2026-03-26 | `tmp/rsi2_lin_exc_rost_review_20261106/LIN_2026-03-11_observation.json`嵌套发行人HTTP200原文hash通过。除息与登记分开存；新capture同样须重新绑定。 |

四项都仅支持该SID/该日/该币种金额和研究支付规则；不支持整个新增持仓区间无其他行动，也不证明券商支付日当天即可交易。

## 尚不能声称完整原文闭包的五项

| 事件 | 现有记录 | 未决 |
|---|---|---|
| CDW 2021-05-24 | USD .40，6/10支付，5/25登记 | batch_ebay_ctsh_cdw_sbux记录SEC URL和web观察，HTTP403，无该条原文捕获路径/hash。 |
| FAST 2022-02-01 | USD .31，3/2支付，2/2登记；provider .155 | batch_fast_khc_bkr_xel仅issuer发布URL/观察；未绑定原文。当前adapter的精确元组只是代码断言，不是单位转换证据。已读冻结早期provider，它的split流只列2019年2:1，不能解释2022现金为何需翻倍；仍需2025拆股坐标桥和名义股数口径证据，不能仅凭恰好2倍准入。 |
| PEP 2023-06-01 | USD1.265，6/30支付，6/2登记 | batch_pep_txn_csco是发行人历史页的整理观察，无该条原文捕获/hash。 |
| CSX 2025-08-29 | USD .13，9/15支付，同日登记 | batch_mrvl_csx_pcar有发行人URL与普通现金标记，HTTP403，无该条原文捕获/hash。 |
| BKR 2024-08-06 | USD .21，8/16支付，同日登记 | batch_fast_khc_bkr_xel有发行人PDF URL与观察，无该条原文捕获/hash。 |

这五项的批次文件和provider来源hash已验证；金额除FAST外与provider一致。但不能用“旧研究曾接受过”替代缺失的原始来源绑定。本轮未扩大检索以寻找未引用的潜在文件；这是当前有界闭包缺口，非断言本机任何位置均不存在。

## 对接边界

先在隔离检查中重绑上述四项，要求新旧provider金额和时间戳精确相等（XEL采用已保存的单事件舍入见证），并核SID、来源hash、事件唯一性及原始金额单位。不复用旧区间的无行动结论，不因已找到一个股息就放行整个新持仓窗口。所有九项本次均保持未准入，生产不变。
