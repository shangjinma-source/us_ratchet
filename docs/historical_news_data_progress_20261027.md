# 历史新闻接入：数据整备进展

## 后续批量整备（同日更新）

已新增全价格域离线构建器及非日历直接季度提取 V2。V1 保留为早期日历季度政策，不能把两版覆盖混报。V2 只接受同一申报内唯一的 70—105 天直接季度、同比期末间隔 350—380 天且长度差不超过 7 天；不从累计数或年度数推算季度，也不合并不同收入概念。

| 窗口 | 全价格域证券 | 有事实候选证券 | 去重候选申报 | 指标事实候选 |
|---|---:|---:|---:|---:|
| 2021—2023 | 122 | 85 | 716 | 1391 |
| 2024—2026/7/30 | 127 | 99 | 684 | 1366 |

清单为 `tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json`，绑定 330 个来源文件哈希；同 CIK 的不同证券 ID 不重复累计事实。候选不是原文已核验事件，不是交易信号，不代表全季度完整覆盖。所有缺失与冲突均保留，不能视为“无负面新闻”。

补取 10 份 SEC 数据文件，包含 SMCI 申报、SNDK 财务数据、META 历史归档及早窗七股申报；原有财务缓存继续复用。早窗 18 个实际持仓/成交证券均找到历史身份映射候选，其中 ENPH、FTNT、LCID 又取得首暴露前的原始财报封面，CIK/代码/类别/接受时间核验通过。这是具体时点的身份依据，不是全生命周期 PIT 认证。

独立代码审查后，原文数字复核增加官方 URL 中发行人 CIK/申报编号与原文 hash 收据绑定、context 实体 CIK、重复 context/unit 拒绝、不支持转换阻断匹配；历史无 CIK 归档必须父文件列表与官方 URL/hash 绑定。修复后原两份财报 18 项选定数字仍匹配。相关四套测试共 21 项通过。

实际发现 SNDK 同一申报接受时间在两份缓存中相差五小时，批量提取器已按冲突拒绝，未默默采用较新值。这说明时间证据不能只检查字段非空。进一步核验收据单独保留，未修改旧缓存或生产建议。

对此仅追加三次官方请求：当前 submissions 与 SGML 头的纽约时间相互一致；旧响应 hash 与旧 manifest 一致，但未查明差异形成于官方版本还是旧采集阶段。index 请求 403 后未重试。证据在 `tmp/sndk_acceptance_conflict_20261027/`，提取器仍拒绝冲突，不将研究推断悄悄写回原数据。

已对三类人类研究机制做有限筛选，见 `docs/candidates/news_mechanism_screen_20261027.md`。优先待评估的双重负面业绩意外需要公告前同口径预期及首次公开时间；现有季度同比数据不能冒充这些输入。仍未启动新闻经济回测，也没有将研究接入交易。

批量清单可重跑：

```powershell
D:/python/python.exe -B scripts/build_historical_sec_event_inventory_v1.py --coverage tmp/historical_news_coverage_20261027/coverage.json --supplements tmp/historical_sec_gap_fetch_20261027/receipts.json --supplements tmp/historical_sec_gap_fetch_20261027/held_identity_receipts.json --identity-candidates tmp/historical_news_identity_20261027/mapping_candidate.json --fiscal-quarters --output tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_recheck.json
```

## 结论

本轮交付离线财报事实提取、原始申报数字核验和全证券域缓存清点。新闻交易规则与增量经济回测仍未完成，生产策略未改；不能把本报告当作采用新闻交易的依据。

## 已完成代码与证据

- `scripts/extract_sec_quarter_events_v1.py`：按精确 SEC 接受时间、申报编号、同指标同单位取直接季度同比。冲突值、缺时间和不能明确的季度排除；不用最新 frame 回填历史。当前仅日历 Q1—Q3，不能概括为所有财年/全年覆盖。
- `scripts/review_sec_original_facts_v1.py`：核对原始 inline-XBRL 的期间、单位、缩放和符号，排除分部上下文；不猜不支持的数字变换。原始文件所属申报以调用者提供的官方 URL 收据绑定，脚本本身不是下载器或申报身份认证器。
- `scripts/audit_historical_news_local_coverage_v1.py`：从两个冻结账户抽取全价格域与实际持仓/成交域，清点已声明公开缓存目录中的身份、companyfacts、submissions 和时间记录。

两套新增单元测试共 8 项通过，涵盖未来申报隔离、季度混用、冲突值、负利润、原文符号/缩放和分部上下文。MRNA、APP 分别在早窗覆盖 9 次申报、后窗覆盖 7 次申报的候选事实；这些不是买卖信号。

实际下载并核验的 2022Q2 原始文件：

| 公司 | accession | 匹配的选定数字数 |
|---|---|---:|
| APP | 0001751008-22-000016 | 10 |
| MRNA | 0001682852-22-000042 | 8 |

原始来源：[APP 10-Q](https://www.sec.gov/Archives/edgar/data/1751008/000175100822000016/app-20220630.htm)、[MRNA 10-Q](https://www.sec.gov/Archives/edgar/data/1682852/000168285222000042/mrna-20220630.htm)。数字匹配不等于所有正文语境、最早新闻时间或全样本都已核验。原文、hash、下载时间与复核报告保存在本地 `tmp/sec_original_filing_check_20261027/`。

## 当前缓存覆盖（存在性，不是准入证明）

| 窗口 | 全价格域 | 实际持仓/成交 | 已定位 submissions | 已定位 companyfacts | 至少有一条区间接受时间 |
|---|---:|---:|---:|---:|---:|
| 2021—2023 | 122 | 18 | 82 | 82 | 80 |
| 2024—2026/7/30 | 127 | 16 | 109 | 120 | 109 |

后三列按全价格域计。早窗证券 ID 不含冻结 CIK，当前 ticker 匹配只能提供线索；后窗冻结 CIK 可复用。所有证券的历史完整性仍标 `NOT_ESTABLISHED`。逐证券证据在 `tmp/historical_news_coverage_20261027/coverage.json`，不要把“至少一个接受时间”当作完整历史事件覆盖。

## 下一步及研究边界

先补实际策略证券的历史身份与申报版本/原文/时间，再扩展候选证券覆盖；禁止只挑亏损股票作经济样本。随后冻结一个有依据的事件机制，复用现有完整账本比较收益、回撤、恢复时间、换手与错失上涨。需要按事件分支重新计算后续选股，不能沿用基准持仓路径。

[SEC 官方 API 文档](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)说明 frames 选取最后申报事实，且 submissions 与 XBRL 处理有延迟。因此按原 accession 与保守可用时点使用，不能在接受瞬间假定全部数据已可用。

不将同比恶化等同于业绩低于市场预期，也不预设财报后漂移今天仍有可执行收益。[Christensen、Timmermann、Veliyev 的研究](https://arxiv.org/abs/2601.08962)在其样本中发现 2016 年后公告后策略收益与有效定价一致，是必须考虑的反证，不是对本策略的直接测试结果。

本轮未调用新模型、未运行经济回测、未更改账户或生产配置。保持年化并降低回撤的目标仍未被证明。
