# 配置化候选服务的统一路由入口

`build_configured_routes` 在后台工作线程启动前，一次装配账户、每日建议、月目标接口、当前目标授权日历及 native HOLD 新闻减仓回调。它检查实际新闻 pipeline 与新闻服务、每日服务的对象身份，以及月目标和日历接入标记；未接入的 helper 不算完成。

该入口保持 `production_activated=False`。它不启动或停止8010，不更改真实账本，也不负责生产切换、行情真实性认证或后台线程退出。生产生命周期切换和真实事件验收仍未完成。

后续生命周期接入：`build_configured_app` 使用同一prepared router，挂载实际DrainMiddleware，退出时在工作线程内以30秒总限调用ServiceQuiescer。统一路由先安装ReviewWorkerOwner；协调器依次等待HTTP、新闻发现线程、独立复核线程，未结束则报NATIVE_SERVICE_SHUTDOWN_INCOMPLETE，绝不授权自动切换。原 `build_configured_routes` 单独返回不等于已挂载HTTP drain，正式候选入口须使用app构造器。

定向验证：协调器两项真实HTTP/线程测试0.411秒通过；实际FastAPI嵌套路由lifespan与shutdown挂载测试0.009秒通过（仅路由准备替身，实际middleware/协调器/owner）。完整API59393与根源码修改发生交叉，不作为冻结版本通过证据；待其终态后由固定版本最终API回归验证。这些测试均未改变8010服务。

验证范围：已有配置化 HTTP 测试改为调用此统一入口，保留现金确认、建议、隔离成交、幂等、现金再确认和后续建议断言，增加实际新闻日历的目标/提案绑定及接入标记检查。根线程运行42958终态exit0，1项125.893秒通过。此 HTTP 测试的 worker 启停为替身，不证明真实线程退出，也不调用模型生成新闻判断。HOLD 回调的经济价值与新闻 API 完整来源绑定均不由这些工程断言证明。

HOLD回调独立集成3278通过137.808秒：指定股票恰好SELL 1股、其他无单，来源记录和review摘要一致，原信号/目标/账户/风险状态不变，加仓和实际provider子类审核失败拒绝。最终统一入口回归使用了包含该入口的更新源码清单，普通建议仍沿相同protected composition执行。
