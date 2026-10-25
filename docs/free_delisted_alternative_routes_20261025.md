# 免费退市历史的三条备用路线核查（2026-10-25）

目标是完整牛熊阶段的 V27 个股回测，年份不锁定。此次只查三个提供方，不注册、不付费、不运行第三方代码。没有把页面宣称当作已取得行情。

| 路线 | 实际核查结果 | 下一步 / 判断 |
|---|---|---|
| WIKI Prices 历史归档 | ML4T 提供方文档声明覆盖 1962—2018、3199 股票、约1540万行，含退市公司；最后观察日2018-03-27。页面只提供本地 Parquet 读取接口，未提供归档下载文件。 | 最值得继续：寻找公开归档，优先检查2008熊市前后；必须实际核对 XLNX、ATVI、CELG 的日期、字段及历史成分股，不能仅凭文档认定无幸存者偏差。已将检索线索交给 GitHub 并行路线。 |
| FinzData | 官网明确免费层只含最近12个月日线；更长历史收费并需API账户。 | 免费条件下不能补全已退市样本；本轮不注册、不购买。 |
| HistoricalData.net | 搜索中的 ATVI 独立页面实际跳转通用股票页。完整日线归档收费；免费样本仅 TSLA、KO、SPY、TWTR 的2022年7—12月。 | 样本可用于字段格式学习，不能补全 XLNX/ATVI/CELG，也不构成完整牛熊个股数据。未下载或运行样本内附脚本。 |

## 原始证据

三个来源页面均实际 HTTP 200 获取，原始 HTML、地址、最终地址、字节数和 SHA-256 保存于本地 `tmp/free_delisted_alternative_routes_20261025_v1/manifest.json`，全部标记 `admitted_for_backtest=false`。

- https://ml4trading.io/docs/data/providers/wiki_prices/
- https://finzdata.com/historical-stock-data
- https://historicaldata.net/stocks.html

WIKI 教程说明的字段包括未调整 OHLCV、ex-dividend、split_ratio 和调整后 OHLCV；这是格式线索，尚非本轮实际文件验证。公开教程见 https://github.com/PacktPublishing/Hands-On-Machine-Learning-for-Algorithmic-Trading/blob/master/data/get_data.py 。未执行其代码。

## 收束边界

本轮排除了两个“免费展示但完整历史收费”的来源，并将可继续方向收敛到 WIKI 归档。没有证明所有免费来源不可行，也没有要求等待开盘。取得实际归档后应先做缺口矩阵和单位核验，再决定覆盖区间，不应先删除缺失股票或用收购方价格替代被收购方。
