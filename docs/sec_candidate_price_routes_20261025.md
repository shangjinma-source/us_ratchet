# 2007年9月名称候选的真实报价路线

使用`scripts/build_sec_candidate_price_routes.py`读取已存SEC名称候选、WIKI全覆盖统计、Yahoo探测manifest及QSTK实际CSV，生成`tmp/bull_bear_membership_diagnostic_20261025_v1/sec_candidate_price_routes.json`。输入SHA随报告保存，无网络与经济搜索。

全部100行保留：99名称候选中88存在至少一条报价候选路线，11暂无路线，另1个Novellus/NVIDIA身份冲突不指定ticker。11个为NIHD、FWLT、VMED、MICC、CDWC、AMLN、BEAS、CEPH、XMSR、CKFR、SEPR。

这是2007-09-30快照，不能取代随后新增成员全域。路线有数据不代表足够253训练会话或全执行区间。88条也不是已认证88只：同名需查发行人/类别，别名需日期证据，单位及公司行动均未准入。

旧MNST明确只查MWW路线，禁止误用Monster Beverage的MNST历史。GOOG旧Class A查GOOGL；ERTS→EA、WFMI→WFM、UAUA→UAL、RIMM→BB及JOYG→JOY仍按未认证路线标注。QSTK使用真实有限OHLC日期，JAVA尾部NaN不能冒充后续交易。

最低风险测试`tests/test_sec_candidate_price_routes.py`验证：不存在的数据无路线，MNST不能串饮料发行人，JAVA尾NaN不延长finite_last。

测试已直接调用通过。另生成`tmp/bull_bear_membership_diagnostic_20261025_v1/event_review_queue_20070930_20081231.json`，从锁定最新jmccarrell YAML提取9组事件，4组与已读官方证据精确一致，5组待核，不改变原分母。

本轮新解决两项：[Nasdaq 2007-10-01公告](https://ir.nasdaq.com/news-releases/news-release-details/henry-schein-inc-join-nasdaq-100-index-beginning-october-2-2007)确认10月2日开盘前HSIC替换MXIM；[Nasdaq发布于GlobeNewswire的公告](https://www.globenewswire.com/news-release/2007/10/03/366533/6948/en/Leap-Wireless-International-Inc-to-Join-the-NASDAQ-100-Index-Beginning-October-8-2007.html)确认10月8日开盘前LEAP替换CDWC。该网站发布时间显示10月2日20:00 ET，URL日期为10月3日，不将URL日期误当生效日。

这独立支持SEC 9月末存在MXIM与CDW，反驳旧CSV提前HSIC；公司行动与旧股票最后可交易日仍须另核。另两组已匹配为2007/2008年度调整。尚未核的事件不因社区表正确计数就自动通过。

后续固定9组复核见`event_review_queue_v2.json`：8组完整匹配，BIDU于2007-12-04加入已确认，但公告未写删除CKFR，保留部分待核。四项新增完整官方事件为[DTV/BEAS](https://ir.nasdaq.com/static-files/15d2a5fe-9b8e-454f-a128-7881eb9f6959)、[CA/TLAB](https://www.globenewswire.com/news-release/2008/05/13/378195/142560/en/ca-inc-to-join-the-nasdaq-100-index-beginning-may-19-2008.html)、[FLIR/UAUA](https://ir.nasdaq.com/static-files/b9791ba8-3448-42e5-bf8c-04c7fb24e3e9)、[STX/旧MNST](https://ir.nasdaq.com/static-files/368db5ec-c029-4078-994a-4895db68889f)。[Oracle 8-K](https://www.sec.gov/Archives/edgar/data/1341439/000119312508094248/d8k.htm)另确认2008-04-29 BEAS每股19.375美元现金转换；指数替换是4月30日，最后成交日/日内时点/现金到账仍未知。

`scripts/build_candidate_forward_membership.py`已生成独立`forward_membership_v1.json`，15个自然月末队列，保留未决SEC身份占位和CKFR事件阻断，不把自然月末当交易决策日。不提供经济结果、不覆盖原来源；后续覆盖计算应基于此审查域扩展新成员，不能继续使用污染的135标签域。
