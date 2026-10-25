# CERN 训练缺口已补为完整价格候选

真实来源为 [abr-98/Stock_prediction_approach_modified 固定版本 CERN.csv](https://github.com/abr-98/Stock_prediction_approach_modified/blob/7be1b54938b9d24f146b8e09959807bb039d559f/stock_details/CERN.csv)。920 行，2017-05-10—2021-01-04，字段 Date/High/Low/Open/Close/Volume/Adj Close；使用 Close，不以 Adj Close 替代。SHA256 `836b6b232183e4e375afad961064c462182c74c7715f9cda0d33044d8ead9c2e`。没有运行项目代码。

固定来源规则：2021-06-07 起使用完整 Quiver 可见段；2020-12-17—2021-06-04 使用 ChartExchange；此前用本次 GitHub 归档。合成结果 613 行，2020-01-02—2022-06-07，相对保存的 AAPL 时间戳参考日历无缺失、多余或非法 OHLC，原 96 日训练缺口全部填补。此参考日历不是独立交易所日历。

GitHub/ChartExchange 重叠 11 日，44 项 OHLC 均在 0.00501 美元内；成交量 11 日不同。ChartExchange/Quiver 重叠 254 日，18 项 OHLC 超过此容差，最大 0.09 美元；成交量 5 日不同，保留明细。SEC 2020-12-31 隐含名义 close 78.4800000623 与候选 78.48 一致。局部价格一致不等于收益或行动链已认证。

另核同作者 Stock_prediction_hybrid_model 固定版本：CERN 仅到 2020-06-22，无新增覆盖；两个完整树均没有 XLNX，XLNX 17 日缺口未解决，不继续扩大本路线。下载仅两张 CERN 表；第三方许可不冒充证券数据再分发许可。

交付目录 `tmp/abr_gap_probe_20261026/`：原 CSV、树、来源/hash manifest、`CERN_price_candidate.csv`、`CERN_audit.json` 和可复现 `build_cern_candidate.py`。仅 price-only candidate，股息、并购现金和身份边界另行核准；未改生产、未提交。
