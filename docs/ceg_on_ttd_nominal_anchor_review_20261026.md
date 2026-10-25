# CEG、ON、TTD 官方名义价格锚

已补三项实际 QQQ 官方持仓名义锚；未修改旧一月输入、未进行经济搜索。

| 股票 | 报表日 / 实际报价日 | 股数 | 市值 USD | 隐含名义价约 |
|---|---|---:|---:|---:|
| Constellation Energy (CEG) | 2022-12-31 / 12-30 | 4,362,408 | 376,083,194 | 86.21 |
| ON Semiconductor (ON) | 2023-12-31 / 12-29 | 7,880,853 | 658,287,651 | 83.53 |
| Trade Desk Class A (TTD) | 2023-12-31 / 12-29 | 8,165,529 | 587,591,467 | 71.96 |

[2022 年末 SEC 原表](https://www.sec.gov/Archives/edgar/data/1067839/000175272423047901/edgar.htm)复用已有来源，CEG 名称/数值行 104/108。[2023 年末 SEC 原表](https://www.sec.gov/Archives/edgar/data/1067839/000175272424049569/edgar.htm)中 ON 行 434/438、TTD 行 313/317。

三个实际保存 Yahoo 原 close 均与官方隐含价格相差小于 0.000002 美元，名义单位 factor=1 支持通过。年末为周末，因此比较前一个真实交易日，不伪造周末报价。此单日锚不替代整窗行动语义核验。

成功证据为 web 工具表格文本；新 2023 请求原响应为 403，明确区分，不假称拿到 SEC HTML。原始价格文件 SHA256、原响应 SHA256、来源、日期、股数、市值、精确商及差异见 `tmp/ceg_on_ttd_anchor_20261026/three_anchor_review.json`。已直接交 scope agent。
