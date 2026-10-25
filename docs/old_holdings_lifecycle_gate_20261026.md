# 出域旧仓：行情终点与权益门槛

成员被移除只改变后续选股资格，不能删除旧持仓及其价值。逐日行情应覆盖持有期间，至实际卖出或已审核的权益转换；不能要求退市后继续存在 OHLC，也不能用最后收盘价虚构卖出。候选池预收行情不等于经济执行准入：未解决行动只在实际持仓或新目标暴露时触发门槛。

本地清单及 13 份来源 hash：[生命周期清单](../tmp/old_holdings_lifecycle_gate_20261026/review.json)。下表仅整理事实与尚需接入的权益规则，不授权经济执行。

|证券|已核事实与来源|实际暴露时必须处理|
|---|---|---|
|SPLK|最后交易 2024-03-15；3/18 盘前收购完成，每股现金 157 美元。[Nasdaq ECA2024-132](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-132)；[本地核验](../tmp/ea_splk_lifecycle_20261026/review.json)|现金权益与可用现金分开，不能猜到账日。|
|ANSS|最后交易 2025-07-16；7/17 盘前完成。最终每股 199.91 美元＋0.3399 股 SNPS，不是初始方案 197＋0.345。[Nasdaq ECA2025-373](https://m.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-373)；[SEC 完成公告](https://www.sec.gov/Archives/edgar/data/1013462/000114036125026141/ef20052066_8k.htm)；[本地核验](../tmp/anss_terminal_bridge_20261026/review.json)|现金、SNPS 应收与零股现金分别处理；指数 7/28 移除日不是股票交易终点。|
|WBA|最后交易 2025-08-27；8/28 盘前完成；8/29 正式暂停交易。每股 11.45 美元＋1 份不可转让 DAP 权利。[Nasdaq ECA2025-463](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-463)；[SEC 8-K](https://www.sec.gov/Archives/edgar/data/1618921/000119312525190603/d87240d8k.htm)；[新补证](../tmp/wba_terminal_official_20261026/review.json)|DAP 取得 VillageMD 相关股权或债权变现净收益 70% 的相应份额，每权上限 3 美元。价值未知，不能默认 0 或按上限估值；真实现金到账日亦未定。|
|SMCI|2024-10-01 按 10:1 拆股交易，CUSIP 86800U104→86800U302。[Nasdaq ECA2024-451](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-451)；[身份桥](../tmp/midwindow_identity_bridge_20261026/review.json)|实际股数和身份迁移独立于价格坐标还原，同 ticker 不代表 security_id 永久不变。|
|HON|2025-10-30 SOLS 分拆；2026-06-29 HONA 分配后另有真实 1:2 反向拆股，CUSIP 438516106→438516205。[单位核验](../tmp/three_spinoff_signal_review_20261026/review.json)；[官方来源绑定](../tmp/next12_distribution_execution_binding_20261015_v1/binding.json)|供应商 1061/1000、1907/2000 是价格坐标因子，不可直接当股数比例；子股应收、到账和零股需显式处理。|
|SIRI|供应商记录 2024-09-10 的 1:10 因子，同时存在重组身份问题。[既有核验](yahoo_2020_anchor_coordinate_review_20261025.md)|当前资料足以定位价格坐标问题，但未在此批准新旧证券完整兑换映射；实际旧仓跨事件应停在该门槛，不能套普通 split。|

旧生命周期 JSON 中 WBA 的“终止事实未绑定”是保留的早期状态，现由独立新补证覆盖；不改写旧文件或其 hash。新材料为保存的 web 工具解析文本，不冒充原 HTML。Nasdaq 页面虽列 8/25 发布，正文包含后续完成更新，不将 8/28 完成事实倒填成 8/25 已知。

未到账现金及未交付股份权益须纳入总权益，但不可用于买入配置。价格覆盖、身份映射、行动事实、实际到账与权益估值是不同门槛；本轮未运行收益回测，也未解除全部行动门槛。
