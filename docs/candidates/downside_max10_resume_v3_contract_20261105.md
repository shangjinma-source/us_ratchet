# Downside max10 v3：多代精确续接，待根审后启动

不修改v1/v2或原策略、成本、退出规则。最新父 `tmp/downside_max10_20261105_late_v2` 有83日账本、累计5次新选择、376.81472619995475秒；祖父late_v1贡献2份sidecar、父新增3份。每份原样保留所属代的research_source_hashes，不统一改写成最新contract。

`docs/candidates/downside_resume_chain_20261105.py` 递归核祖先源码pins、parent_file_hashes、继承预算、逐代账本前缀、sidecar完整性及完整account arguments。累计new等于祖先累计加本代新选择记录数，replayed仅本轮记录，不算新搜索；防循环及跨workspace路径。递归只读，不调用选股。

`scripts/research/run_downside_account_candidate_20261105_v3.py` 为v2独立衍生文件。重放全部五次父选择，完整参数逐字段相等才复用；逐日核最新父83行前缀，未完成不得新搜索。最终再核全部父链文件hash和账本前缀。预算继续累计，后窗最多31次新选择/10800秒、单月600秒，不重新获得额度。

附加股息由freeze中的artifact列表接入，META原10笔与CEG已审配对分别保留源pins。逐笔核SID、除息、支付日、USD名义金额、零预扣研究假设、来源引用和原provider观察；不重复已有事件，不将供应商复权金额替代已审名义数。复杂行动准入未放宽。

准备入口 `python -m scripts.research.prepare_downside_max10_resume_v3_freeze_20261105 --artifact <CEG路径>=<独审确认SHA256>`；未取得已审CEG配对artifact前不生成最终freeze。该入口只冻结依赖和父链，不执行经济计算。

根审后实际入口：`python -m scripts.research.run_downside_account_candidate_20261105_v3 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v2 --output tmp/downside_max10_20261105_late_v3`。当前未启动。

三项夹具已通过（2.44秒）：真实两代2+3来源绑定及累计预算；完整参数污染/第83行前缀污染拒绝；普通股息配对金额污染及重复事件拒绝。不是经济验收。
