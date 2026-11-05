# Downside max10 v4：配置式多代续接

不重写账务、选股或续接逻辑。新入口 `scripts/research/run_downside_account_candidate_20261105_v4.py` 私有加载已冻结v3模块，仅注入v4 freeze读取器；旧模块文件和其他进程命名空间不变。实际计算完全沿v3 `run`，使用既有通用父链helper。

父 `tmp/downside_max10_20261105_late_v3`：146日、累计8次新选择、609.5263517999556秒；三代sidecar归属2+3+3。全部完整参数和各代source pins保持；最新146日账本前缀完全相等之前不能新搜索。累计10800秒/31次、每月600秒不重置。

freeze沿v3的META和CEG配对材料，加已独审AZN/CTSH ordinary dividend artifact列表，比例/名义单位按原审查，不因供应商舍入或普通股/ADS差异强行改金额。只增加精确账务证据，不降低策略门槛或增加新公司行动适配。

准备命令（仅冻结，不经济运行）：

`python -m scripts.research.prepare_downside_max10_resume_v4_freeze_20261105 --artifact <已审路径>=<SHA256>`

每份新增artifact单独重复参数；输出目录存在则拒绝覆盖。根审并批准后唯一经济入口：

`python -m scripts.research.run_downside_account_candidate_20261105_v4 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v3 --output tmp/downside_max10_20261105_late_v4`

本轮准备不自动启动；只读验证真实三代父链与146行边界，不重跑经济。
