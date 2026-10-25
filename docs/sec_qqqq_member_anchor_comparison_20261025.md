# SEC基金持仓与历史成员独立交叉核查

实际读取`tmp/nasdaq_official_membership_20261025/qqqq_20070930_holdings.csv`（2007-09-30持仓）及锁定commit的jmccarrell 2007 YAML，按其日期事件正向计算至9月30日；旧社区CSV取当时最近快照。SEC表100公司、jmccarrell100标签、旧CSV102标签。基金持仓不自动等同指数名单；公司名称也不能代替证券类别和ticker有效日期。

## 名称级真实差异

| SEC持仓公司名称 | 旧CSV | 新YAML | 含义 |
|---|---|---|---|
| Electronic Arts Inc. | EA | ERTS | 同公司线索，旧标签可能现代化，须历史ticker有效日 |
| Symantec Corporation | NLOK | SYMC | 同公司线索，不能用后来的NLOK当时点标签 |
| Liberty Media Corp.（一行） | QRTEA及LMCK | LINTA | 只支持一行公司持仓；不支持未来LMCK，LINTA类别仍需核 |
| Monster Worldwide, Inc. | 未见对应独立旧MNST | MNST | 官方2008年材料确认旧MNST是独立招聘公司，不是HANS饮料公司 |
| Maxim Integrated Products | 缺失MXIM，存在HSIC | MXIM | SEC支持MXIM；新源把MXIM→HSIC事件放在2007-10-02，仍需官方事件确认 |
| Discovery Holding Co.（一行） | DISCA及DISCK | DISCA | SEC仅一行公司，不能支持额外未来C类的简单回填 |
| 没有Endo公司行 | NDOI | 无 | 旧源NDOI无独立持仓支持，并有2024才交易的官方冲突证据 |
| Novellus System, Inc. | 无NVLS | 无NVLS | SEC文本列Novellus而两个社区未含，必须解决差异 |
| 没有NVIDIA公司行 | NVDA | NVDA | 与上行共同形成一个待核差异；不能按数量相等就认证名单 |

Novellus行6312070股、价值228749417美元，隐含价格约36.24；已请原始SEC提取agent复核公司名称，不能根据价格猜测改成NVIDIA。其余名称仅可作为人工候选对齐，未建立100条已认证证券身份。

新旧源字面差异：新独有ERTS/LINTA/MNST/MXIM/SYMC；旧独有DISCK/EA/HSIC/LMCK/NDOI/NLOK/QRTEA。新源改善明显，但上述Novellus/NVIDIA差异及具体股份类别未解决前，不能升级为官方完整指数分母。

可恢复身份优先级：旧MNST→Monster Worldwide（后续MWW报价路线）、ERTS→Electronic Arts、SYMC→Symantec、LINTA→Liberty对应类别、MXIM→Maxim。每条仍分别需要有日期的身份、真实价格与公司行动；不以名字相似自动拼接。官方基金表只是独立证据，任何纠正均另存版本并保留原始分歧。

## Novellus/NVIDIA有限独立追查

父agent与原提取agent均复核SEC原文确为Novellus，不是本次解析误标。五组定向搜索得到[NVIDIA官方2001时间线](https://www.nvidia.com/content/timeline/time_01.html)确认早年加入，但[Nasdaq 2004年调官方公告](https://ir.nasdaq.com/static-files/ab256567-5f82-43b4-b441-967c4e5ececf)含NVIDIA退出，因此不能用2001加入推定2007连续成员。

2005-12-19重新纳入NVIDIA及删除Novellus有当年报道与[Rice研究原文历史变更表](https://repository.rice.edu/server/api/core/bitstreams/06d99659-f1e5-49e7-926f-38be93783596/content)线索；尚未恢复Nasdaq当次官方公告或同日期另一基金报表，未将该线索视为已解决SEC标签冲突。保留原SEC行，优先下一份独立基金披露或官方指数公告核定，禁止用相近价格替换公司名。

最后补查[NVIDIA FY2007 10-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581007000008/fy2007annualreportonform10-k.htm)，没有找到Nasdaq-100文本，未增加区间资格证明，停止该重复路线。其余99行继续整理为`tmp/bull_bear_membership_diagnostic_20261025_v1/sec_company_identity_leads.json`：保留全部100原公司名及行号，99条人工名称候选ticker，Novellus行ticker为空并带冲突标签。每条identity_admitted与index_membership_admitted均为false，股份类别仍需核验；这是审核队列，不是正式100股分母。
