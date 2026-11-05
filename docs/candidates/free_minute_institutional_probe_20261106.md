# 新增机构公开分钟来源：有界核查

2026-11-06。本轮不注册、不付费、不调用模型、不启动策略回测。此前 FirstRate、HF IEX、Dukascopy 的结论不重复计算为新成果。

## 结论

新增取得 QuantConnect 官方 LEAN 仓库的 AAPL 三个连续交易日成交分钟样本，可用于数据读取和成交量字段的技术验证；**尚未取得支持主线牛熊经济验收的完整分钟资料**。Databento 官方测试数据只有极短截片。没有因这些样本而改变生产或宣称截图策略已经验证。

## 实际下载

| 来源 | 实际范围 | 样本结果 | 可用边界 |
|---|---|---|---|
| QuantConnect/Lean | AAPL 2014-06-05、06-06、06-09 | HTTP 200；686、783、834 条；每天常规时段 390 条；时间无重复，OHLC 包络和非负量检查通过 | 前两日可作受限技术验证；6/9 拆股日整体未认证，不用于收益 |
| Databento/databento-python | XNAS.ITCH NVDA，生成脚本指定 2020-12-28 | 公开分钟 DBN 下载 HTTP 200，187 字节；脚本明确 LIMIT=4 | 单 Nasdaq 交易所测试截片，非连续交易日资料；未解码认证实际最早/晚时间 |

LEAN 文件路径：[AAPL 分钟目录](https://github.com/QuantConnect/Lean/tree/master/Data/equity/usa/minute/aapl)。[官方格式说明](https://github.com/QuantConnect/Lean/blob/master/Data/equity/readme.md)注明美东时区、时间为午夜后毫秒，价格除以 10000，Volume 为成交股数；2007 后供应商 AlgoSeek，TradeBar 过滤可疑逐笔后聚合。不是 CFD BID 量。样本缺少逐交易所明细，不额外宣称本次独立认证了 SIP 全成交完整性。

6/9 04:00 原始行：`14400000,6455700,6455700,922300,924200,600`。换算为 O/H 645.57、L 92.23、C 92.42，混合拆股前后尺度。不能仅删除这根 bar 就认定其余整日可用于收益；跨日价格、成交股数及公司行动需要一致单位审计。前两日亦仅技术样本，未与独立成交带交叉认证。

仓库分钟目录包含 AAPL、AIG、BAC、FOXA、GOOG、IBM、NWSA、SHY、SPY、TWX，但只实取 AAPL；目录中的历史证券不证明完整退市覆盖或无幸存者偏差。实际抽样最早/晚日如上，不推断整个产品历史覆盖。

Databento [生成器](https://github.com/databento/databento-python/blob/main/tests/data/generator.py)通过历史 API 抽取且限制四条，不是本轮自造数据，但本轮没有解码 DBN，也没有确认四条的准确时间、调整单位或连续性。无法用它代替完整分钟回测。

## 许可与证据

LEAN 根目录 Apache 2.0 许可证已保存；没有将代码许可证推定为第三方交易所数据无限再分发许可。样本仅本地研究，不加入公开数据包；Databento 截片的数据许可/调整单位尚未认证。完整商业产品及 SDK 可访问不等于免费数据全库授权。

本地证据：`tmp/free_minute_new_sources_20261106/`，含三个原始 ZIP、原始格式说明、Databento 生成器及 DBN、下载收据、检查结果。`manifest.json` 为各保存文件的 SHA256 和字节数；ZIP 的 URL/HTTP 状态/哈希/首末原始行在 `checks.json`。常规时段不填充缺失分钟。

另对 AlgoSeek sandbox 入口做了只读可达性检查（HTTP 200 页面），没有取得行情，也未证明免账号下载；不计为第三个有效数据来源。收到收束指令后停止，不继续注册或查找。

## 下一可选路径

免费样本可用于明确标记为技术验证的分钟读取、信号时序和单位异常拒绝测试；主线程同期核验 HF 官方条款：下载/API 需要账号，且仅限 academic/educational、禁止构建或校准真实资金策略；因此本轮不把 HF IEX 列为免账号可落地替代源（见 https://hfdatalibrary.com/pages/terms 及既有探针追加记录）。真实全域、连续牛熊、历史退市证券及公司行动一致的分钟资料仍缺，不将该缺口隐藏成收益结论，也不启动样本经济回测。
