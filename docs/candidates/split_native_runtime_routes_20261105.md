# 新月目标 HTTP 现金与成交承接隔离验证

`tests/test_split_native_runtime_routes_20261105.py` 使用实际 monthly factory 生成目标、持久化 proposal、拆股账本、分钟行情解析与限价算法、native composition、正式账户/current/news 路由；日信号 reader 仍是明确控制夹具，不是来源认证。

最终根线程复核：`D:/python/python.exe -B -m unittest discover -s tests -p test_split_native_runtime_routes_20261105.py -q`，1 项综合测试，3.281 秒，OK。

- 现金 POST 后 current 返回 READY，账户和建议 revision 一致。
- HTTP DIRECT_FILL 在临时账本卖出 1 股后持仓减少 1，事件只增加 1 条；同一请求重试账本不变。
- 旧新闻 bound_context 被拒绝；未重新确认现金时 current 返回 409 / CASH_RECONFIRMATION_REQUIRED。
- 成交不会推断券商购买力：原已确认现金数值保留但失效，用户再次输入可用现金后恢复建议。首次新增断言误期望自动加卖出款，已依据 ledger 的既有语义纠正测试；生产现金算法未改。
- 确认现金后刷新，待卖股数减少 1，账户/current/news 绑定一致，原月目标不变。
- 新闻 worker 生命周期启动、关闭各一次；测试不启动模型、不对外联网。

受控时钟前进一分钟后再次读取的报价仍在时效内，测试没有声称捕获到现实市场的新一分钟行情。所有现金和成交均为临时合成账户；未写真实账户、未下单、未部署。完整 source reader 与此 HTTP 链的组合仍待完成。
