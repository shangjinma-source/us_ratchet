# 年度质量同版本描述数据：实际产物

已运行，无新增下载、排名、选股、收益测试或账户写入。复用原23截面，原候选域2322行全部保留；1885行有可描述的同accession年度NI、OCF、期末Assets。

|资料层|公司×截面行数|
|---|---:|
|明确时区acceptance换算纽约后早于截止日|1436|
|仅filed日期严格早于截止日|449|
|无兼容同版年度三字段|277|
|ticker→CIK线索缺失或不唯一|153|
|已有映射但companyfacts文件缺失|7|

每个可计算行保存SID/ticker/CIK、concept/USD、精确分数财务值、start/end、accn、各字段全部filed日期、acceptance原值与纽约时间、源文件哈希，并计算NI/期末Assets、OCF/期末Assets、(NI−OCF)/期末Assets。资产必须正数；负NI/OCF保留原值。未提供者无比率，不填0。GrossProfit若存在仍沿旧选择规则核同版唯一数值，未拼造毛利。

保留原版本排序（期末、Assets filed、accn），严格同accession/同年度起止与唯一值。所有不合格与未选版本原因保留。带时区acceptance如果不早于截止日，明确拒绝；无时区不能进入精确接受层。采用比截止当天收盘更保守的前一纽约日边界，非完整交易时间认证。

产物：
- `tmp/annual_quality_local_diagnostic_20261106/summary.json`：小汇总与源hash。
- `tmp/annual_quality_local_diagnostic_20261106/descriptive_panel.json`：所有2322行，去掉重复raw observations/拒版明细，保留字段精确值、版本、时间、缺失状态、源hash和完整记录pointer；适合后续读取。
- `tmp/annual_quality_local_diagnostic_20261106/result.json`：完整104MB本地原料诊断，包含raw observations及拒版记录，不应作为Git附件；panel绑定其sha256。
- 脚本：`scripts/research/describe_annual_quality_local_20261106.py`；运行约5–7秒。
- 测试：`tests/test_annual_quality_local_diagnostic_20261106.py`；6组通过，覆盖截止后accn不能补缺字段、不同accn/start不拼接、冲突/非正资产拒绝、精确比率、接受时间与时区、companyfacts内CIK与映射CIK去前导零后的精确身份一致性。

原稿认证局限仍在：后下载companyfacts同accession可能被事后修正；ticker/历史域身份只为条件性线索；未重认证inline XBRL全部context/transform/unitref，未完成修订链。本产物是可得原料子样本描述，不能称完整QMJ、PIT认证或经济优势。原文核验标志保持False不代表数值不可描述，也不冒称此轮已核原文。

身份加固后已重新运行：2322行/1885可用保持不变；实际身份不符0行。若不符则保留行标COMPANYFACTS_CIK_IDENTITY_MISMATCH，不生成比率。
