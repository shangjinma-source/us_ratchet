# XLNX 最后 17 日行情缺口：实际归档数据已取得

按明确单文件 URL 下载 [tsaustin 美股历史价格归档](https://www.kaggle.com/datasets/tsaustin/us-historical-stock-prices-with-earnings-data)。ZIP 483017860 字节，49.4 秒完成，SHA256 `abfa90acb153de738b9f681d120d34e96823ff50b771497d4fcb47922fbbc58c`。只用 zipfile 流式扫描内含 CSV 一次，不将约 2GB 文件全部读入内存，不运行第三方代码。

XLNX 提取 5899 行，1998-01-02—2021-06-11，无重复日期。2020-08-03—08-25 所缺 17 个参考交易日全部存在，实际数据单独保存为 `XLNX_17day_gap.csv`。字段 symbol/date/open/high/low/close/close_adjusted/volume/split_coefficient；使用 close，不混用 close_adjusted。

与已有 GitHub 归档 147 个重叠交易日比较，全部收盘在 0.00501 美元内一致，仅 4 个其他 OHLC 字段超过容差；与 ChartExchange 200 个重叠交易日全部 OHLC 均在容差内。详细差异与原始值保留，不声称整份历史已经认证。

同时提取 DISCA 4011 行，2005-07-08—2021-06-14，无重复日期；不覆盖当前需要的 2021 年末后继数据缺口。

文件在 `tmp/xlnx_tsaustin_20261026/`：唯一 ZIP、下载 manifest、两证券实际 CSV、17日子集、`extraction_audit.json` 与可复现本地脚本。原始数据未推送；price-only admission 仍需与固定来源候选整合，经济行动独立核准。未改生产、未提交。
