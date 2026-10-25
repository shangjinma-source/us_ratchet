# 历史成员来源污染核查

结论：thuningxu/sp500nq100社区CSV目前不能作为牛熊回测主分母，只能保留线索。第二YAML来源同样包含现代标签，不能以相互吻合认证。不能直接删除可疑证券凑齐名单。

## 官方证据

- LMCK：发行人[2014年第二季披露](https://www.libertymedia.com/investors/financial-information/sec-filings/content/0001560385-14-000047/exhibit991lmcq22014earning.htm)明确新Series C于2014-07-24开始regular-way交易。CSV与第二YAML却把LMCK列入2007—2010，不能解释为普通缺价，属于时间身份不成立。
- NDOI：[Endo发行人公告（Nasdaq刊载）](https://www.nasdaq.com/press-release/endo-announces-commencement-otcqx-trading-2024-06-28)说明2024-06-28以NDOI在OTCQX开始交易。[2015年10-K](https://www.sec.gov/Archives/edgar/data/1593034/000159303416000051/endp-12312015x10k.htm)为ENDP。CSV从2007出现NDOI，尚无支持该早年身份的证据；不能把新破产重组权益简单接旧股历史。

## 源代码机制核查

下载但不执行[build.py](https://github.com/thuningxu/sp500nq100/blob/main/build.py)，本地冻结`tmp/bull_bear_membership_diagnostic_20261025_v1/community_build.py`。`build_nq100`从当前名单倒推，每个事件用`cur=(cur-add)|rem`；缺失加入事件、错误的删除代码会把未来证券持续带回早年。NQ_CANON与NQ_RENAMES没有LMCK、NDOI对应修复。已确认存在传播机制，尚未取得该版本生成用原始wikitext，不能断言具体哪一事件造成这两个污染。源代码未认证完整事件链，最新名单匹配也不能证明历史正确。

## 第二来源年初对照

已实际冻结[第二项目](https://github.com/shardul0701/NQ100-Survivorship-bias-data-2004-2026/tree/main/src/nasdaq_100_ticker_history)2007—2010 YAML及SHA，`year_start_source_disagreements.json`保存差异。2007年初CSV无快照，不虚构对照。2008—2010 YAML各101标签：

| 年初 | CSV独有 | YAML独有 |
|---|---|---|
| 2008 | GOOG, HSIC, NDOI, WFMI | GOOGL, MNST, WFM |
| 2009 | GOOG, HSIC, NDOI | GOOGL |
| 2010 | GOOG, HSIC, NDOI, PCLN | BKNG, GOOGL |

这些是字面差异，不是已修正身份。MNST代码复用已获官方证据：[Nasdaq 2008-11-03公告](https://ir.nasdaq.com/static-files/368db5ec-c029-4078-994a-4895db68889f)说明STX自2008-11-10替换Monster Worldwide（MNST）；[Monster Worldwide 2007年报SEC](https://www.sec.gov/Archives/edgar/data/1020416/000104746908001550/a2182830z10-k.htm)确认该发行人。故2008 HANS与MNST不能合并为同一发行人。社区代码全时间`HANS→MNST` canonical折叠会混淆两条历史身份，属于明确机制缺陷。第二来源保留二者并非这项重复错误，但它仍包含早年LMCK及NLOK/QRTEA，不具备直接替换主分母的资格。

下一步需取得当年完整成员快照作锚点，再以官方增删与公司行动正向重建；优先解决LMCK/NDOI/HSIC及代码复用，而非继续盲目下载错误标签。必须保留原分母和差异审计，不将缺失股静默排除。这项数据纠错不依赖开盘。

## 官方年度事件逐项对照与身份校验实现

使用`tmp/nasdaq_official_membership_20261025/verified_events.json`对照实际CSV相邻快照增删及第二YAML事件：2007-12-24双方都精确匹配官方；2008-12-22 CSV精确匹配，YAML删除项用WFM替代官方WFMI，其余一致。详见`official_annual_event_comparison.json`。两次事件正确不抵消初始快照和身份污染，更不能认证全部历史。

新增纯函数`backtest/historical_security_identity.py`：记录格式为ticker、issuer_id、security_id、start/end（闭区间）、source_references；证券ID与发行人绑定不允许冲突，同ticker时间区间不得重叠，解析必须按交易日期，主张的issuer/security须与该日匹配。公司行动不是简单别名，来源参考仍需外层真实性审核。

`tests/test_historical_security_identity.py`三项测试通过：HANS与2008旧MNST保持不同issuer、错误跨issuer映射拒绝；LMCK不得回填至2008；重叠或证券发行人冲突拒绝。测试边界是示例夹具，不是完整历史身份数据库，未生成假完整100股名单。
