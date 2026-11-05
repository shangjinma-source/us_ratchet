# 新月原生目标的受保护执行入口

`NativeSplitRollingAdmission` 每次通过目标对应 runtime 验证及身份覆盖检查，复制实际 factory Provider，保留其 `_assemble` 的历史单位与三时点审核。若误传基础 Provider，明确拒绝，不把它转换成未经新增审核的对象。

保留原 DailyMarketV3 运输证据、gzip 停牌源、gzip RSS 行动源、报价时效、单次分钟重试以及当日限价库。拆股 timing 来自服务端绑定，限价审核比较实际 unit review 的 timing hash，不依赖上月 transition 数量。

根线程独立复核：`D:/python/python.exe -B -m unittest discover -s tests -p test_split_native_rolling_admission_20261105.py -q`，1 综合测试5.418秒，OK。覆盖实际 factory 生成目标、HTTP现金/临时成交/确认/当前建议/新闻绑定/重新配置幂等；强制子类审核失败会被实际调用；坏停牌gzip不产生BUY，保留原允许的仅卖出回退。

边界：测试 `_for_target` 返回真实 factory runtime，但配置路由为受控适配；日信号 reader 为受控信号，不是最终正式捕获入口。此项不独立证明正式月发布/实时供应商来源或生产部署。已有原始来源→HTTP测试需进一步与此保护入口及正式捕获组合；不改研究policy_id冒充生产许可。
