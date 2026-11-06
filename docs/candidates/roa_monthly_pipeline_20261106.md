# 月末准备流水线：已实现范围与剩余步骤

新增入口 `scripts/research/prepare_roa_monthly_package.py`，默认只做 dry-run。它不改当前活跃源码、配置、金融任务、真实缓存或账户。

## 现有准备入口核查

现有 `scripts/prepare_monthly_captured_training.py::build` 可把已保存全域采集推进为新的条件训练 manifest，已要求全域一致、来源 SHA 与 session closed；`coordinate_monthly_simulation.py` 会串联旧 quantity-v2 的 capture/publish/bind。`build_real_monthly_release_entry.py` 读取旧市场完成包。这些旧绑定包含自身策略规则，因此本轮没有直接调用它们激活 ROA，也未修改原定任务。

ROA 编排消费已经生成且审核的训练 manifest，不重复网络采集，不把上月 manifest 当新月。请求需明确 manifest、完整训练日历、交易时刻日历各自 path/SHA，`expected_month` 与独立输出目录。

## 编排行为

1. 核验所有输入和日历原源，确认训练截止日已经过真实日历收盘时刻。
2. 调用固定 ROA 月选择生成器：253 个交易日精确匹配、月末相邻新月、同版财务、原域缺失原因、固定排序。
3. 要求产物月份等于请求月份；缺输入、未收盘或旧名单冒充新月都拒绝。
4. 显式 `--create` 时，新建不可覆盖目录，保存原 selection，冻结全部 runtime 输入至 `input_bundle/inputs`。
5. 将 runtime selection 的 source pins 改绑 bundle 中原始字节，保留原 selection 作为证据，重新计算摘要。
6. 用正式纯 loader 读取验证；只有选择内容/权重不变才写 `registry.proposed.json` 和 `PREPARED_VERIFIED_NOT_REGISTERED` 回执。

产物没有自动写入任何活跃 registry。失败准备目录保留供核查，没有成功回执不能采用。

## 实际验证

真实 10/30 输入 dry-run 成功：`tmp/roa_monthly_offline_request_20261106.json`、`tmp/roa_monthly_offline_dry_run_20261106.json`。固定十票不变，1,246 个源、355,775,466 字节，未再复制此整包。

4 项测试通过，覆盖真实编排/不可变复制/正式 loader 链路（选股输入用合成替身，不冒称新历史回测）：准备完成后覆盖原财务文件仍从 bundle 加载；盘前、缺文件、11 月输入冒充 12 月拒绝；dry-run 无输出目录；两日历首个执行日冲突或缺失在生成前拒绝。完整重叠日期段也必须一致。加入检查后真实 dry-run 仍通过，记录 `tmp/roa_monthly_offline_dry_run_20261106_v2.json`。实际选股本身另有真实 10/30 全结果一致测试。

## 尚需真实事件或操作

- 新的真实月末收盘、全域行情/身份/公司行动及财务资料准备，生成对应 manifest；现无真实 12 月名单。
- 审核准备回执，将 proposed registry 在一次受控正式发布中纳入配置并重新 pin、重启验证。脚本不会自行执行这一步。
- 新月首个交易日行情、实际已有持仓/未成交委托和成交录入验证。
- 若未来要自动定时生成或注册，需要另行把该入口接入批准的月任务；本轮未更改现有金融任务，不宣称整个月换已无人值守完成。
