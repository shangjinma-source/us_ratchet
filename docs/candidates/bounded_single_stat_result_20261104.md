# Bounded source gate：单次元数据读取候选

完整候选strategy_bounded_source_gate_single_stat.py随后随同余额刷新修复一起部署，见docs/cash_noop_live_acceptance_20261104.md。仅合并_no_links中每层is_symlink/exists/lstat为一次lstat，检查S_ISLNK及Windows reparse属性。缺失路径继续检查祖先，最终文件存在检查仍拒绝。原_read_digest的前后路径检查、完整流式hash、字节上限、fstat/stat竞态校验不变。

8项候选回归通过：源/配置变更、相同路径单次读取、符号链接、祖先reparse、缺失文件、同长度同mtime字节篡改、流内修改、读取后替换链接、预算和只读配置约束（部分在同一测试内）。

当前活动链343个唯一源码文件作为相同输入，先分别记录metadata调用次数，再六轮交替AB/BA无计数开销测试。两版本每次读取全部字节并与当前批准hash一致。

|指标|原版|候选|
|---|---:|---:|
|metadata调用数|11331|4463|
|6次中位耗时|0.157880秒|0.077384秒|

调用减少60.6%，该组件读取耗时约减少51.0%，绝对节省约0.0805秒/完整唯一文件集合。此测试没有复现生产每层/每次重复gate路径，也没有测current接口，不能将组件百分比外推到53秒建议刷新。旧profile显示多次gate累积数秒，因此存在价值，但最终是否部署应按总收益和发布成本决定。没有继续扩大参数或修改缓存。

私有可复现脚本tmp/benchmark_bounded_single_stat_20261104.py，结果tmp/bounded_single_stat_20261104/result.json。六轮均候选更快；文件热缓存和并发负载仍限制绝对耗时外推。
