# 带生产保护的统一HTTP成交闭环

组合已提交的SplitProductionRollingAdmission、三时点reader、拆股账户router、V30/V32快照和真正新闻服务。受控行情经过原始provider执行、gzip停牌/RSS、时间校验、限价和cap store；不以basic composition代替保护入口。

根独验：`D:/python/python.exe -m unittest discover -s tests -p test_split_protected_runtime_routes_20261105.py -q`，session79841自然退出0，1项综合测试14.328秒通过。

实际临时HTTP路径：保存AVAILABLE_AFTER_RESERVATIONS且保留未结买单→正确WAIT→撤单和确认→当前建议卖拆后A16股→POST DIRECT_FILL成交16股→原请求幂等重试→确认余额→获取下一分钟报价→current不再建议A、news context同一新账户版本。真实NewsInvestmentService.bound_context拒绝成交前绑定；没有伪造真实模型COMPLETE，也未测试模型对收益的贡献。

最初缺成交resolver身份原文时正确拒绝，夹具随后补充同resolver已验证原字节；同一分钟旧限价输入拒绝新账户，改为真实下一分钟采集，没有放松时间或身份门槛。真实SQLite记录、原始行情解析和HTTP路由运行，外部数据均为合成，实际网络禁止。worker只验证单次生命周期，不运行外部新闻抓取。

限制：monthly._for_target仍为测试边界固定原provider/runtime；跨月release/训练单位认证、生产源码发布授权和成组激活尚未完成。未写真实账户、未下单、未切换线上策略。
