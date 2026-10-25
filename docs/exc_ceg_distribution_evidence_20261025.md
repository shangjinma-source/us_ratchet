# EXC → CEG：分拆权益及价格坐标证据

仅研究映射；未改生产、未向回测注入事件，未假定汇丰到账时间。

## 已确认事实

| 字段 | 证据结论 |
|---|---|
| 法律生效 | 2022-02-01 00:01 ET，不能直接当作 regular-way 经济除权时点 |
| 股权登记 | 2022-01-20 17:00 ET；不是单凭该日持仓机械确定最终权益 |
| 除权日 | 2022-02-02；EXC 2/1 收盘前 regular-way 交易仍带 CEG 权利 |
| when-issued | CEGVV 从 2022-01-19 交易 |
| regular-way | CEG 从 2022-02-02 交易 |
| 权益 | 每 3 股 EXC 得 1 股 CEG；母股 EXC 股数不变 |
| 零股 | 聚合出售、现金分配；金额及投资者到账时间仍未知 |

来源：[完成分拆 8-K](https://investors.exeloncorp.com/static-files/96e979a6-d649-4a2a-8e43-95bfd34c67b6)、[发行人 Form 8937](https://investors.constellationenergy.com/static-files/9a7b24f2-4a36-4f22-9ad9-831673c6c085)、[BOX/OCC 49979 通知](https://boxoptions.com/assets/BOXOnnMemo205387.pdf)、[CEG 一季度公告](https://investors.constellationenergy.com/news-releases/news-release-details/constellation-reports-first-quarter-2022-results)。OCC 通知在 2/1 发布并给出次日除权；8937 为事后确认。OCC 期权交付规则不能冒充股票券商到账规则。

## 现有 schema 映射

对于只交易 EXC regular-way 的账本，建议经济事件 `effective_date=2022-02-02, timing=BEFORE_OPEN`，以 2/1 收盘实际 EXC 持仓创建子股权益，然后才执行 2/2 订单。该日期是经济除权映射，法律生效时间须单独保留。`parent_ratio='1'`，`child_ratio='1/3'`，`post_parent_sid=parent_sid`。待证券主表确认 CUSIP：EXC 30161N101、新 CEG 21037T109。不能与 2012 年前旧 CEG 身份合并。

`eligible_parent_quantity` 必须从实际回放状态绑定；三项 confirmation 需完成身份、挂单处理和时序验证后设置，证据模板不直接设为 true。不要填 delivery/payment 日期。整股未到账权益按当日 CEG 价格估值但不能用于买入；零股现金金额不明时现有模块会明确阻塞，不能凭 close 猜金额或永久忽略。

## 价格坐标及具体数据

`tmp/exc_ceg_distribution_20261025/local_quotes.json` 保留原始响应 hash 和事件附近 OHLC。Yahoo CEG 查询包含 1/19—2/1 when-issued 数据，不能因此提前放入 regular-way 买入域。EXC Yahoo splits 的 1402:1000 是回填价格坐标，不是母股数量增加。恢复事件前名义 OHLC 的候选操作是乘 1.402，2/2 起不乘；须独立名义价格锚点验证后准入，不依 SEC 差值硬修，不用 adjusted close 替代，不把成交量和普通现金股息金额一并盲乘。

2/2 Yahoo EXC 高低均值为 41.945，CEG 为 53.015，与 8937 名义价格例子约 41.95、53.02 一致。这只检查事件后坐标，不足以单独证明事件前全路径。ILMN 2024 和 CMCSA 2026 的分拆在 2021—2023 窗口外，只需恢复源价格坐标，不生成窗口内持股事件。

原始下载记录在 `tmp/exc_ceg_distribution_20261025/manifest.json`：BOX PDF 成功，SHA256 `0a9159453add1cd3175035437db9a9e1341dd1f649461192242ed12460db6772`；两条 Exelon 直接下载 403，未冒充原始 PDF。网页解析证据另存 `web_parsed_evidence.json`。可落实的下一步是独立名义价格交叉验证及权益模块联调；经纪商到账、零股现金未知不能被默认补齐。
