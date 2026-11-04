# 五份年度财报：限定官方获取结果

本轮已停止，保守按10个请求操作计入上限。五份accession固定，未扩域、未下载全量、未选股/回测，未修改生产或EMA代码。

本地SEC直接抓取器要求真实联系标识，本进程SEC_USER_AGENT未配置；没有使用example.com占位身份或读取凭据。使用官方网页读取工具核查公开SEC页面，得到3份年度报告的可读文本，**没有取得可供既有inline-XBRL context提取器处理的原始HTML文件**。因此不能报告“5份原文已落盘”或“12字段完整验证”。

| 公司 | 已核实结果 | 剩余缺口 |
|---|---|---|
| GILD | 2020年度OCF为8,168百万美元，与原accession companyfacts一致 | 年度原HTML/context、其余收入字段和修订桥 |
| REGN | 2020年度OCF为2,618.1百万美元，与原accession companyfacts一致 | 年度原HTML/context、收入字段和修订桥 |
| MNST | 现金流表显示1,364,163，数值对应companyfacts的千美元表达 | 返回片段未包含单位表头，不能单靠此片段认证量纲；仍缺原HTML/context及其余字段 |
| CHTR | 指定年度索引工具不可访问，未返回可判定HTTP状态 | 原HTML与精确接受时间仍缺；没有称为已确认403 |
| ZS | 指定年度索引工具不可访问，未返回可判定HTTP状态 | 原HTML与精确接受时间仍缺；停止该项 |

来源：[GILD年度原申报](https://www.sec.gov/Archives/edgar/data/882095/000088209521000008/gild-20201231.htm)、[REGN年度原申报](https://www.sec.gov/Archives/edgar/data/872589/000180422021000008/regn-20201231.htm)、[MNST年度原申报](https://www.sec.gov/Archives/edgar/data/865752/000110465921029943/mnst-20201231x10k.htm)。GILD/REGN接受时间沿此前已核本地SEC submissions，未利用2022未来年度比较值替代2020原版。

请求计数：首批请求5个地址但工具仅返回3条；随后2个索引读取与3个原页面数值定位。按提交的操作数保守计10，不再额外请求。未绕过访问限制或更换网站重复穷举。

证据位于`tmp/five_annual_official_fetch_20261105/receipt.json`及两份web_extract文本。SHA256仅绑定工具返回提取文本，不是SEC原HTML哈希；每项明确URL、accession、表格行、量纲是否可见及缺失context。完整PIT TTM认证仍未通过，本轮结果只增强两条OCF原申报文字证据。
