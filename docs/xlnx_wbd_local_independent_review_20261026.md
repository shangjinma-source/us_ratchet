# XLNX 固定桥接与 WBD 前身单位本地复核

只读核查，不改根脚本、不运行经济研究。

## XLNX

输出 2020-01-02 至 2022-02-11 共 534 行，来源分配 164 行 tsaustin、116 行 ChartExchange、254 行 Quiver。固定切换为 2020-08-26 / 2021-02-11；逐行原 OHLC 与标记源文件完全匹配，全部输入/输出/参考日历 SHA256 一致。相对已保存 AAPL 会话参考，缺日/多余日/重复均 0。

特定 17 日缺口 2020-08-03 至 2020-08-25 的小 CSV、原始 tsaustin 文件及桥接输出三者四价完全匹配，读取 `close` 而非 `close_adjusted`。脚本先排除 2020-01-02 以前行，因此 2019 年坏 OHLC 不进入已冻结研究范围；本结论不认证更早数据。

证据：`tmp/recent_price_bridges_20261026/XLNX_independent_review.json`。

## WBD / DISCA

对 `tmp/xlnx_tsaustin_20261026/DISCA.csv` 与 `tmp/wbd_routes_20261026/WBD_stock_data.csv` 做 2020-01-02 至 2021-06-14 重叠四价比较：365 日，364 日所有原 OHLC 在 0.011 美元容差内一致。唯一差异为 2020-04-01 Open：DISCA 比 WBD 少约 0.1293002289；当日 Close 差约 0.0049992371，仍在上述容差内。差异保留，不拼接改价。

2020-12-31 DISCA 原 Close 30.0900、WBD 原 Close 30.0900001526。该长段一致性支持两份原价序列的相同名义单位，结合主线程已有 DISCA→WBD 1:1 官方承接证据，可作为前身价格单位佐证。它不是新的 SEC 官方市值锚点，也不能宣称全部四价完全一致。

建议保留完整 Zenodo 作为固定 WBD 价格来源，不因单个开盘差异择价；是否允许该差异应在数据准入记录中明确，独立复核没有静默替换价格。

证据：`tmp/wbd_routes_20261026/disca_unit_overlap_review.json`，含两文件 SHA256 及完整差异。
