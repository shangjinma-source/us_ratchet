# ROA/动量固定融合与 LRCX 价格身份独立审查

已只读独立重建全部67个月名单：资格只用同月合法候选和不晚于决策的季度面板；NI/OCF>0、Assets>0；字段filed严格早于季度cutoff。两个精确Fraction指标的低到高平均秩/N各50%，高分优先、同分SID、issuer去重后前10，与实际输出逐项一致。未发现反向排序、先截前10再融合、未来季度资料混入或issuer重复。年度版本来源仍只是已声明的局部诊断，不等于历史PIT认证。

早窗每日现金+股票=净值核验通过；独立峰谷回撤21.695189%，期末29714.243107，输出年化14.557031%。晚窗2024-09-30缺SID时metrics为null，保持严格失败，不给部分年化冒充完整结果。

缺口实际是LRCX，不是KLAC。原roster正确，口头ticker误标未污染代码：LRCX旧SID security:0000707549:512807108，KLA另为 security:0000319201:482480100。固定split mapping只6项，**没有LRCX事件**；不能因为其source_hashes有ticker就说已有行动映射。

现有 `tmp/relative_strength_downside_20261106_2024_2026/execution_inputs.json` 的 document.dated_identity_transitions 已明确LRCX2024-10-03旧512807108→新512807306，share_ratio10，且标注identity_quote_binding_only，不是正式经济转换准入。引用prepared文件SHA 226210854041216e8ace37fb52395809d6cff64e45e2f125197da9e2f7047606已核匹配。document OHLC旧股至2024-10-02，新股从2024-10-03至2026-07-30，边界单位分别约814美元与81美元。

已核既有原始provider `data/cache/research/current_raw_capture_20261014_v1/LRCX.response.bin` SHA3432b85b9111a4a581fa4da50af2042cc0ea684d201ad2d28cfb076afdca992c；其splits事件timestamp1727962200为2024-10-03、numerator10/denominator1。前一批10/13原文SHA dc61b07b8744f044f356a0894ecce2c11d99fde431a08840da23684c681be626亦与document pin一致。

可供隔离价格诊断的精确桥：只给上述旧SID、指定9/30月段，10/02及以前用旧OHLC，10/03起新SID收盘×10建立旧股等价价值；同日open/close比例用新SID同一bar，无需再乘10。必须绑定execution/prepared/provider来源hash和完整交易日，拒绝错日期/错SID/错比例。不要将其认作真实股数转换、现金分红、零股或税收完整认证，不开放生产gate。未新采集、未新跑收益。

## 原单候选补全后复核

LRCX精确桥完成后重新只读核验两窗source pins与账本。早年化14.5570308%、回撤21.6951890%、期末29714.243107；晚年化28.0204022%、回撤25.5774525%、期末37109.488112。每日现金守恒/非负、独立指标重算通过。上文晚metrics=null是原partial状态，现partial独立保留；不得将其误报为当前仍缺口。

全周期验收不得机械要求每一子窗都双优QQQ。连续账户尚待补2023年12月及身份边界，不能直接拼两个独立20k结果声称全期已通过。

## 连续窗身份边界预审

`tmp/roa_continuous_identity_boundary_20261106.json`保存10项旧research SID到canonical SID及source pins。使用早季度面板CIK与晚prepared身份记录中唯一且2023-12-29在观察/可用范围内的证券绑定，非ticker直接拼接；META为30303M102。12/29双方OHLC九项精确一致，ODFL各字段约1.7e−6美元差异保留（来源坐标重建微差）。只可用于声明过的条件诊断别名迁移：保留资产价值/现金/pending，不按更名制造卖买费用，后续使用晚源自身锚点收益比；不是正式历史身份认证或经济公司行动准入。仍需检查连续runner实际实现。
