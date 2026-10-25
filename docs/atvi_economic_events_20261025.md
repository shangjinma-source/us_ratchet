# ATVI最小经济事件清单

普通年度股息金额、登记日与支付日已找到发行人/SEC来源；毛金额与用户未知税率分开，不因税率暂停。未跑收益。

| 年 | 毛额USD/股 | 除息日候选 | 登记日 | 官方支付日 |
|---|---:|---|---|---|
| 2020 | 0.41 | 04-14 | 04-15 | 05-06 |
| 2021 | 0.47 | 04-14 | 04-15 | 05-06 |
| 2022 | 0.47 | 04-13 | 04-15 | 05-06 |
| 2023 | 0.99 | 08-01 | 08-02 | 08-17 |

金额/登记/支付来源：[2020 SEC发行人公告](https://www.sec.gov/Archives/edgar/data/718877/000110465920056888/tm2018444d1_ex99-1.htm)、[2021 SEC 8-K](https://www.sec.gov/Archives/edgar/data/718877/000110465921012239/tm213853d1_8k.htm)、[2022发行人公告](https://investor.activision.com/news-releases/news-release-details/activision-blizzard-announces-second-quarter-2022-financial)、[2023发行人8-K](https://investor.activision.com/static-files/7cb83643-154f-4a1f-9101-17e9c059f1e5)。web工具可读相关文本，直接HTTP下载403如实留存，不伪称取得原文文件。

除息日证据须分级：2020/2021由已有归档复权因子分别跳变对应约0.409997/0.470001美元及公开日历相互印证；2023已有Quiver页面0.99注释。2022-04-13由公开股息日历列出，尚未获得发行人/交易所原除息通知，不能把登记日前一日机械推定（2022-04-15为特殊假日时序）。它是当前最具体的日期证据缺口，不否定已核金额/支付日。

归档2022-04-13前后Adj.Close/Close均1，没有反映0.47股息；这再次说明不能用其Adjusted Close代替真实股息收益。保存 `archive_exdate_corroboration.json`，不是用复权列计回测收益。

## 收购与停止交易

[Nasdaq ECA2023-588](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2023-588)实际HTTP200：2023-10-13交割日全天暂停交易，10-16起停牌，每股现金对价95美元。[SEC完成收购8-K](https://www.sec.gov/Archives/edgar/data/718877/000110465923108985/tm2328253d1_8k.htm)确认10-13普通股取消并转为95美元现金领取权。由交易所通知与价格末行一致支持最后正常交易日10-12；不能把10-13或之后的数据商重复94.42行当成可成交日。

95美元领取权不等于券商当天现金可买入。实际到账日未查明，应转应收并终止旧股；除非有明确统一研究支付假设，不直接增加可用现金。股息官方支付日同样不能证明真实用户券商入账时点。

## 拆股与适用边界

本轮未发现2020—2023拆股；[发行人可核旧拆股公告](https://investor.activision.com/news-releases/news-release-details/activision-blizzard-two-one-stock-split-now-effective)为2008-09-08。这支持候选“期内无拆股”，但单条旧公告不是完整负面证明，机器清单明确negative_evidence_complete=false。不能从查不到公告推定已完成全事件认证。

结构化清单、来源状态及哈希在 `tmp/atvi_economic_events_20261025/economic_events.json`、`source_manifest.json`。净额暂不填写；明确研究税模型后由已实现的账法计算，不把未知实际税率当成数据不存在。
