# 新闻预算锁加固：已测试，尚未部署

当前已部署并真实验收的是V27 r7：单服务内的新闻任务互斥、10分钟间隔及持久记录的北京时间每日4次预算。

独立审查发现多服务实例并发可能同时通过预算判断；初始JSON记录写入中断也可能造成后续无法校验。候选改为SQLite事务登记，记录进程身份和运行占用，保留旧预算并在不确定时拒绝新任务。

候选：`docs/candidates/news_refresh_service.py`；5项验证：`tests/test_news_refresh_service_v2.py`。仍不保证辨认父进程结束后的遗留模型子进程，发布前不得把这一限制描述为完全解决。

部署准备已保存本机 `tmp/frontier_capture_refresh_20261027/`：`active_r8.json`、`news_refresh_service.py.r8.pending`、`news.js.r8.pending`，以及 `research_contracts/frontier_runtime_20261027_v27_r8/server.json`。R8包含加固及状态中文文案修正。

自动审批拒绝了短暂重启8010的部署命令，仅给出“blocked by policy”。整个命令未执行；当前已恢复与r7相匹配的源码，72项pin全匹配、月目标GET200。没有留下一半部署或关停服务。用户确认问题已提出；收到明确同意后再应用两份待部署文件、核对r8 pins并短暂重启。

旧新闻任务已成功结束，历史JSON可迁移；不得删除旧记录以绕过预算，也不得将尚未部署的候选写成线上能力。

## 后续整备：R9为最新待部署包

在等待确认期间补齐了Moderna实质公告来源，最新组合包在本机 `tmp/news_release_20261027_r9/manifest.json`，包含5份源码和 `active.json`；配置为 `research_contracts/frontier_runtime_20261027_v27_r9/server.json`，73项pins。R8准备材料保留作历史，但新部署应使用完整R9包，不能混用清单。

R9同时包含预算锁、状态中文文案、公司公告来源及无内容新闻过滤。仅列表和最多两篇正文的有界采集，无新增后台定时任务。来源核查取得真实公司正文，后续解析测试5项、低信息过滤3项通过；新来源尚未接入线上或完成新来源的模型端到端验收。

公司来源链由[Moderna官方投资者页面](https://investors.modernatx.com/)链接的发行服务确认。相同股票主题中也有律师和市场评论，因此检查公司发布声明、代码与联系方式，不能仅凭ticker标签当官方公告。Sandisk官方分发正文获取失败，保留元数据覆盖限制。
