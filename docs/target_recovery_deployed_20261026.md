# 10月26日恢复修复已部署，盘中验收仍未通过

用户明确授权短暂重启8010并部署。当前生产为 V27 r4，策略规则与账户不变。

## 已上线并核验

- 页面版本失配已解除，账户及月目标GET均返回200。
- 页面内和跨页面目标恢复已接入，原事件编号持久化、跨标签串行恢复；恢复不重复写现金。
- 补齐恢复脚本静态路由；实际HTTP返回200，资源hash与部署配置相符。
- 复核器对空目标/建议明确返回稳定错误，不再出现AttributeError，也不将缺失结果视为通过。
- 67项生产源码pin匹配。部署后及盘中采集后账户与部署前一致，没有下单或真实现金写入。
- 本轮10项针对性测试通过，包含4项真实浏览器/临时HTTP/SQLite恢复验证。选股及行情仍为测试输入，不当作实盘证明。

活动配置：`research_contracts/frontier_runtime_20261026_v27_r4/server.json`。
配置SHA256：`33dd87a725306b8b3bf3242bdd6308d985fe5a39cc2045bdcbb7daea7f471c0c`。

## 真实盘中复测

北京时间23:18页面采集完成，目标可读，但建议返回 `DAILY_PREVIEW_UNAVAILABLE`，因此有效报价、整数股数、限价和现金限制的本次盘中验收未通过。

直接诊断后端原因为 `SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW`。已保存的两只股票日线均无events，相关证券公告匹配无blocking。RSS接收于15:17:38 UTC，频道时间正常；DN2026-3、DTN2026-22两条技术公告发布时间为17:00 UTC，晚于接收时间。`saved_frontier_first_window_v1.py` 对任意条目未来发布时间的全源检查造成阻塞。没有通过跳过校验或改写来源时间强行生成建议。

此问题仍待有范围约束的公告相关性处理或新有效来源。不能说已完成盘中建议验收。真实成交承接仍待用户实际策略成交，月底准备和新月采用按实际事件验收。

## 本地私人证据

- `tmp/target_recovery_release_20261026_v4/before_deployment/`：回退文件及部署前账户快照。
- `tmp/target_recovery_deployment_r4_receipt.json`：配置、源码pin及账户不变检查。
- `tmp/real_intraday_acceptance_20261026_after_recovery_r4/`：页面、截图及网络时序。
- `tmp/target_recovery_r4_preview_trace.txt`：实际后端异常定位。

上述原始证据保留本地，不上传私人账本。既有定时任务未变；22:05一次性提醒已执行并删除，未创建重复提醒。
