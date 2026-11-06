# 免费分钟回调执行实验结果

2026-11-06，MECHANISM_PROXY_NOT_DEPLOYABLE。已实际运行，不是仅格式检查。结论：当前有限样本没有支持分钟提前入场优于次开盘的经济证据，不部署、不扫描阈值。

|样本|会话|前日趋势及量能合格日|盘中触发|A分钟臂已观察|A缺数据未知|观察期不足|B次开盘形态已失效|B存活未知|两臂完整有效配对|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|IBM|64|9|5|2，均止损|1|2|2|1|0|
|AAPL|10|10|6|4，均止损|0|2|4|0|0|

A臂已观察6笔全部为-1R（计划风险包含双边5bp滑点），独立20k/单股10%notional上限计算的price-only损益分别IBM -13.767740美元、AAPL -17.9233125美元。这不是完整账户亏损：各事件独立、未复利、未计算股息税和HSBC月佣金、未知与尾部未完成事件不算0收益。数额小的原因是持股10%notional上限先约束，不能解读为已满足真实账户风险目标。B臂对应6笔因原止损已被穿越而不入场，不得把它们记成获利交易；有效配对为0，paired_price_pnl现返回null，明确没有可比较收益，不再输出容易误读的空集合0。

IBM 10/29触发后12:26缺一分钟：A持有路径未知，B到次开盘前形态是否一直存活也未知，不能看后来的行情补判。11/2与11/3触发不足5会话。AAPL10/27与10/30同属尾部不足。全部保留在事件表，没有按结果删除。

样本与暖机：IBM raw分钟和同源462日raw日线，399日事前暖机、63重叠OHLC精确；AAPL FirstRate ZIP内10日regular分钟，各390条，与Kibot raw日线10重叠日OHLC四项全精确，满足固定253日初始化。数据坐标吻合不是完整供应商/公司行动认证。IBM非原NDX域；AAPL这10天不能代替历史牛熊研究。

截图与本实验区别：真实Martin有市值/波动/AVWAP与盘中结构等条件且长期保留趋势余仓；本次无PIT市值、不伪造AVWAP，采用前日趋势+首次开盘区间突破后的阴线回调，再完成分钟突破前bar高点，下一分钟open。固定3R全出/5会话观察是执行机制假设，不声称原版复制。此前日线代理需等收盘确认，IBM零确认结论仍成立；这是明确不同的新机制实验。

代码审查修复后已重新运行：只用已结束bar生成信号；未来缺分钟不删除早先信号；确认后执行bar缺失保留事件并标UNKNOWN；共同交易日历纳入日线中的缺失分钟整日，不能把下一可见日偷当下一会话；B先检查原形态存活与真实nextopen距离；同bar止损和目标冲突先止损。3个本地防未来/未知断言通过，独立agent另5个缺分钟/缺整日/同bar冲突反例已保存为tests/test_minute_pullback_independent_20261106.py，并由主线程以unittest复验通过。pytest不可用，采用直接调用测试函数，没有安装依赖。

复现：
- `D:/python/python.exe -m scripts.research.ibm_minute_pullback_mechanism_20261106`
- `D:/python/python.exe -m scripts.research.aapl_minute_pullback_mechanism_20261106`
- 冻结合约：docs/candidates/ibm_minute_pullback_contract_20261106.md
- 逐事件/筛选记录/源码和源哈希：tmp/ibm_minute_pullback_20261106/result.json、aapl_result.json
- AAPL原ZIP：tmp/free_minute_sources_20261106/AAPL.zip；warmup原文/receipt及坐标核对同结果目录。

停止此样本扩展，不以6个止损断言原投资者体系无效，也不继续围绕这11个事件微调规则。当前没有提供收益超过QQQ且最大回撤<=30%的上线证据。
