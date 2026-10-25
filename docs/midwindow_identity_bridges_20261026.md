# 中段9个月：六只证券身份补证

本轮为身份映射元数据的回溯核验，不使用未来财务数值选股，也不改变历史NPORT首次可得日。精确决策桥在 `tmp/midwindow_identity_bridge_20261026/review.json`，原文为带hash的web工具解析文本，非原始HTML。仅限表列决策；没有改变代码或运行经济回测。

|证券|CIK|CUSIP|最早所需决策|新的一手证据日期与身份|
|---|---|---|---|---|
|SMCI|0001375365|86800U104；10/1起86800U302|2024-07-31|2023-02-10 SEC13G及真实filing index；2024-09-24 Nasdaq拆股通知|
|APP|0001751008|03831W108|2024-11-29|2023-02-09签署SEC13G，明确AppLovin Class A|
|AXON|0001069183|05464C101|2024-12-31|2024-02-07签署SEC13G，明确Axon common|
|MSTR|0001050446|594972408|2024-12-31|2024-02-12签署SEC13G，明确MicroStrategy Class A|
|PLTR|0001321655|69608A108|2024-12-31|2024-11-21 Nasdaq DTN2024-30，明确NYSE→Nasdaq同ticker/CUSIP并保留历史|
|SHOP|0001594805|82509L107|2025-05-30|2024-03-22公司SEC会议通知，明确Class A subordinate voting，区别Class B|

对应APP/AXON/MSTR/SHOP签署/通知日期不冒充SEC正式接收时刻；尝试filing index均不可访问，失败亦保存，因此`sec_filed_date=null`。SMCI索引已核2023-02-10、Accepted16:05:21。PLTR为交易所公告日期，不是从晚披露NPORT倒填。即便没有当时抓取存档，这些文件证明既存证券身份，可作为明确回溯身份桥提交根审核，不能声称全数据PIT认证。

SMCI必须分段：2024-07/08/09月末映射旧86800U104；2024-10月末映射新86800U302，10:1股数行动由现有独立事件路径处理。Nasdaq通知为9/24发布、9/30 17:00法律生效、10/1拆股交易；不能把9月通知当7月已知信息，7月旧身份有2023年SEC文件独立支持。APP/AXON/MSTR/PLTR/SHOP不能只因公司名相同跳过证券class，JSON显式绑定原CIK和CUSIP。

该桥可针对原编译器9个月的`IDENTITY_NOT_AVAILABLE_BY_CUTOFF`进行定点复核。原晚NPORT记录保持原样；不要把其字段改成更早日期。价格、行动完整性和经济执行许可均不随身份桥自动升级。

来源网址逐票见JSON。主要官方材料包括SEC各发行人目录13G/6K，以及Nasdaq [SMCI ECA2024-451](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-451)、[PLTR DTN2024-30](https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2024-30)。
