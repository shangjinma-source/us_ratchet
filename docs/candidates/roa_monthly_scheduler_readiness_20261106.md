# ROA 月末准备调度入口（未安装）

- Python：`scripts/run_local_roa_monthly_preparation.py`，通过`python -X utf8 -E -B -m scripts.run_local_roa_monthly_preparation`运行；默认只preview，不导入/执行pipeline，不创建运行日志。
- 安装器：`scripts/install_local_roa_monthly_preparation.ps1`，默认输出任务预览；只有显式`-Install`才创建独立`UsRatchet-ROA-Monthly-Preparation`。不覆盖旧任务；同名任务配置不一致拒绝。
- 固定cwd、Python绝对路径、Hidden、IgnoreNew、StartWhenAvailable、15分钟检查、3小时上限。Interactive登录模式：需要用户已登录，不能声称无人登录也运行。
- descriptor含root/python/request path+SHA/source_pins/log_directory；`make_descriptor`只生成供审核的字典，不自动安装。当前静态源码闭包682项，AST遍历函数内部import、相对导入、package __init__以及字面量本地.py引用；不把任意动态import或所有运行数据算作已静态穷尽。动态配置/数据仍由原pipeline正式gate校验；安装前必须重新生成并独审descriptor。
- 启动前校验descriptor、request和全部静态源码pins；active改变明确`ACTIVE_CHANGED_REBUILD_REVIEWED_REQUEST`，不自动替换hash。
- 显式execute只准备，不adopt。阶段结果/退出码落日志。成功保存prepared marker，后续只做轻量源码/request/active检查，返回待受控采用，不重复完整gate或采集。该marker不是产物重新认证；真正采用前仍须完整publication与adoption复核。
- 非成功错误保存blocked，后续不自动重试；输出不完整、锁遗留需人工核对，不以时间偷锁。正常月末前WAIT可继续定时检查。

## 本轮验证

`tests/test_roa_monthly_scheduler.py`5项通过：preview零pipeline/零日志、成功只调用一次pipeline、active变化拒绝、失败停重试、代码pin/锁、真实闭包关键模块覆盖（后两共一个测试）。真实descriptor预览682pins通过；PowerShell安装器实际执行**不带Install**返回`PREVIEW_ONLY_NO_TASK_REGISTERED`。本地记录`tmp/roa_monthly_scheduler_preview_20261106.json`，descriptor绑定当前12月请求，仅是将来条件式任务准备，不代表12月真实资料已存在。没有运行execute采集、没有安装任务、没有动账户或生产配置。
