# 源码路径检查提速候选（2026-11-04）

候选完整文件：strategy_bounded_source_gate_single_stat.py。生产data/strategy_bounded_source_gate_v1.py未修改。

每个路径节点用一次lstat替代is_symlink、exists和lstat重复状态查询；逐次完整源字节hash、读取前后文件身份/大小/时间检查、Windows reparse与符号链接拒绝均保留，无跨请求缓存。

验证：原bounded gate 4项与新增路径安全4项在候选函数下通过。新增测试覆盖目录reparse、文件缺失、同大小同时间戳内容修改、读取结束后链接替换。新增4项也在未修改的生产代码上通过。候选测试用独立进程替换函数，不修改生产。

交替局部读取500次耗时：原0.229/0.254秒，候选0.109/0.111秒；不能外推整链提升。

同一独立实际服务实例交替四次完整休市建议调用：原19.069/19.198秒，候选16.091/16.107秒，中位数19.1335→16.099秒，节省3.0345秒（约15.9%）。四次均WAIT_POLICY_REVIEW_SESSION；完整账户和目标前后相同。未执行startup hooks、无模型调用，使用诊断内存journal，不写真实建议日志。全链配置构建201.874秒。

与浏览器此前39.837秒整次刷新不同，这里只量建议接口，不能宣称页面40秒已降为16秒。基础文件绑定在V6源配置中；顶层29到该层的base引用链共23层，部署需同步相关引用及preparation源pins，不能仅替换顶层3份配置。

决定：有效候选保留后续合并部署，不为约3秒收益单独重启生产。当前不再扩展同类路径微调；下一步必须解决重复校验的操作边界或其他实际链路缺口。不得将候选或测试通过报告为已上线。

本地证据tmp/source_gate_speed_20261104/checks.json和full_preview_comparison.json；脚本tmp/test_source_gate_speed_20261104.py、tmp/compare_source_gate_preview_20261104.py。
