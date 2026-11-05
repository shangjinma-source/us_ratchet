# 真实 SplitProfiledRouter 至 native daily admission 集成

2026-11-05，隔离临时目录；无生产写入、网络或模型调用。

- `tests/test_split_profiled_native_admission_20261105.py` 直接复用真实发布准备、SplitProfiledActivation.adopt、SplitProfiledRouter、SavedFrontierProposalStore/View 和实际原生选股。
- NativeSplitRollingAdmission 使用真实 router._for_target 返回的配置与 factory Provider；没有替换 router 或构造 _for_target 适配器。
- 运行真实完整分钟行情解码、gzip RSS/停牌运输、限价与每日建议流程，得到 READY、实际 new_orders 与 execution_binding。
- 验证后账户、原目标、提案、活动发布 snapshot 均不变；真实 factory 子类 _assemble 被强制拒绝时，调用链同步拒绝，没有跳过审核。
- 运行命令：`$env:PYTHONPATH='.;tests'; D:/python/python.exe -m unittest test_split_profiled_native_admission_20261105.Tests -v`
- 会话 84448：exit 0，1 项综合测试，30.761 秒 PASS。

边界：财务/日历/行情来源是既有明确合成夹具；信号 reader 仍为 controlled reader，外部运输为受控字节。本测试补齐真实发布路由与保护执行入口的接口证据，不认证真实源，不代表部署或真实券商到账。未修改任何原生产或既有候选源码。
