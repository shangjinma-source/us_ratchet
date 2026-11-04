# AI 复核上下文性能定位（2026-11-04）

在独立进程按当前 scheduled_ai_runtime 配置构建实际服务，不执行 startup hooks、不启动第二个新闻 worker、不调用模型。构建耗时 201.725 秒。一次真实 service.context() 的 cProfile 耗时 16.758 秒；完整账户、月目标前后相同。

主要开销：snapshot provider 14.900 秒，占约 89%；两次历史发布验证 12.382 秒。调用链保留前后发布一致性检查，不能直接删除第二次验证。文件 stat 共 481622 次，累计 6.724 秒；缓存命中仍需完整校验源字节，这是正确性要求。

完整候选文件：docs/candidates/strategy_release_replay_cache_single_stat.py。仅把每个路径组件的 is_symlink/exists/lstat 三次状态查询改为一次 lstat，同时拒绝符号链接及 Windows reparse 属性；缺失源仍交原读入器拒绝。不缓存文件状态、不跳过哈希、不变更缓存键与结果。

验证：原 8 项回归全通过无跳过，覆盖同大小同时间戳篡改、源缺失、计算期间变更、符号链接、缓存隔离、容量、并发；另验证 Windows reparse 属性拒绝。交替顺序 5 轮、每轮 500 次实际源码读取，中位数 0.233 秒降至 0.163 秒（约 29.8%）。仅局部微基准，不能外推为整条复核提速。

本地证据：tmp/news_context_profile_20261104/{report.json,context.prof,context_cumulative.txt,candidate_benchmark.json}。诊断脚本 tmp/profile_news_context_20261104.py 与 tmp/test_replay_single_stat_20261104.py。生产文件未修改，候选未上线。

下一步：在一个独立服务实例中交替对照原与候选完整 context 读取，检查结果完全一致与账户未变；若实际节约有意义，再合并正式源码绑定配置部署。不要为了小幅微基准收益重复重启生产。后续还需判断多次完整发布读取能否在不跨模型等待、不延长报价期限的操作边界内合并。
