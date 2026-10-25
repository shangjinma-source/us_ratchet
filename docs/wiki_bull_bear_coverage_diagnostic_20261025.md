# WIKI历史子集真实覆盖诊断

范围仅用于2008—2010候选可行性诊断，不是用户限定年份，也不据此选择最佳收益区间。状态NOT_ADMITTED，无经济搜索、无生产改动。

实际读取106051条WIKI CSV，保存脚本`scripts/diagnose_wiki_member_subset.py`、成员需求脚本` scripts/prepare_bull_bear_member_diagnostic.py`。原始来源和输出哈希、完整逐日缺口保存在`tmp/bull_bear_membership_diagnostic_20261025_v1/real_subset_diagnostic.json`，分层路线在`layered_coverage.json`。

| 项目 | 结果 |
|---|---|
| 候选日期参考 | AAPL/MSFT/INTC日期完全一致，1034会话；没有独立认证交易所日历 |
| 决策范围 | 2007-12-31至2010-11-30，36个月末，每窗253个候选训练会话 |
| 历史成员标签分母 | 135；99在子集有数据，36缺失；未删除缺失成员 |
| 有数据标签内部缺日 | DISCK缺451个早期日期；其余相对候选日历无缺日 |
| 训练完整标签 | 首窗74/102，末窗83/103；只是日期覆盖，不是证券资格 |
| 行级异常 | OHLC逻辑异常0，重复ticker/date 0 |
| 公司行动字段 | 18条split_ratio非1，497条ex-dividend非0；尚未核实事件经济处理 |

不混合Yahoo与WIKI单位：另有ERIC/FLEX/INFY/LOGI/RYAAY/TEVA六个同名Yahoo候选，TCOM/BB等别名待核。父agent提供HANS→MNST、GOOG旧Class A→GOOGL官方身份线索，仍需价格来源与动作对齐。NLOK/QRTEA等现代标签已经出现在社区早年名单，必须检查历史重建污染，不可仅按字符串匹配认定当时可买。

剩余22标签暂无线索覆盖：AMLN、BEAS、BMC、CEPH、CKFR、FMCN、FWLT、GENZ、JAVA、JOYG、LEAP、LIFE、LMCK、MICC、NDOI、NIHD、PPDI、SEPR、TLAB、VMED、WCRX、XMSR。该清单为当前阶段结果，后续来源可改变；不是宣称免费数据不存在。

最小风险测试`tests/test_wiki_member_diagnostic.py`三项通过：空子集显式拒绝、重复日期可见且缺失成员保留、成员区间裁剪及重复标签拒绝。使用临时目录直接调用测试函数验证（本Python环境没有pytest），没有安装依赖。

正式准入仍需历史完整分母、身份别名有效期、交易日历、复权和名义价坐标、普通股息/拆股/并购/退市及未到账权益审查。候选日历与同名行情覆盖不能替代这些检查。
