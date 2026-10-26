# 新闻预算锁加固：已测试，尚未部署

当前已部署并真实验收的是V27 r7：单服务内的新闻任务互斥、10分钟间隔及持久记录的北京时间每日4次预算。

独立审查发现多服务实例并发可能同时通过预算判断；初始JSON记录写入中断也可能造成后续无法校验。候选改为SQLite事务登记，记录进程身份和运行占用，保留旧预算并在不确定时拒绝新任务。

候选：`docs/candidates/news_refresh_service.py`；5项验证：`tests/test_news_refresh_service_v2.py`。仍不保证辨认父进程结束后的遗留模型子进程，发布前不得把这一限制描述为完全解决。

部署准备已保存本机 `tmp/frontier_capture_refresh_20261027/`：`active_r8.json`、`news_refresh_service.py.r8.pending`、`news.js.r8.pending`，以及 `research_contracts/frontier_runtime_20261027_v27_r8/server.json`。R8包含加固及状态中文文案修正。

自动审批拒绝了短暂重启8010的部署命令，仅给出“blocked by policy”。整个命令未执行；当前已恢复与r7相匹配的源码，72项pin全匹配、月目标GET200。没有留下一半部署或关停服务。用户确认问题已提出；收到明确同意后再应用两份待部署文件、核对r8 pins并短暂重启。

旧新闻任务已成功结束，历史JSON可迁移；不得删除旧记录以绕过预算，也不得将尚未部署的候选写成线上能力。
