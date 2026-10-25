# 旧窗口资料本地保存检查点

为保留本轮取得的资料，已创建独立快照：

`research_contracts/research_archive_20261026/old_window_sources_v1.zip`

- 365 个文件，原始合计 197,245,614 字节，ZIP 32,633,686 字节。
- ZIP SHA256：`d5f5ab4a539a8bb826e46ecf2d93e635c9c4b8793a864e07ba301a1d6af42451`。
- 清单 SHA256：`7405caaa1d234487259ff6e217d5130ace68b928bc3c2de3b2a9a3f11a03be61`。
- 每个压缩条目均重新读出，逐项验证字节数与 SHA256；已有 ZIP 不覆盖。

覆盖本轮成员时间线、初始成员补证、普通上市历史、HONA/SPCX、ANSS 桥接、EA/SPLK 生命周期、名义价格锚、ILMN 坐标和官方交易日历，以及这些资料直接引用的本地文件与原行情盘点中的来源文件。失败下载原件与成功来源分开保留，不把 403/404 页面当作有效公告。

这是**资料保存检查点，不是回测结果或完整可重放环境认证**。旧研究清单作为文件保留，其所有递归依赖没有重复打包；新统一编译器、后续补出的身份桥及独立复核在本快照之后生成，应随下一份检查点保存。原始资料未移动、删除或覆盖。完整 2021—2023 账本另有 [独立归档](research_archive_20261026.md)。

明细位于 ZIP 内的 `EVIDENCE_MANIFEST.json`，外部同内容清单为 `old_window_sources_manifest_v1.json`，读回结果为 `old_window_sources_v1.readback.json`。恢复到单独的空研究目录并保留相对路径，不覆盖正在使用的工作区。原始行情和归档仅留本地；公开脚本及说明推送 GitHub。

通用入口 `scripts/archive_research_evidence_manifest.py` 只处理显式文件清单。已验证准确读回、拒绝覆盖既有归档、拒绝来源变更、拒绝仓库之外路径；归档成功不会改变资料自身的条件性限制。

## 31 窗条件训练完成后的第二份快照

`research_contracts/research_archive_20261026/old_window_training_v3.zip` 保存全部 31 窗统一 raw 训练输入、其显式绑定来源、独立复核、后补身份桥与生命周期证据。

- 960 个文件，原始合计 404,433,938 字节，ZIP 70,920,546 字节。
- ZIP SHA256：`0a0ea2a189a8926f1dcb26fb4b3d69cfc58fc9bd497a33b7308a4efa3f18eb98`。
- 清单 SHA256：`74807ffbc38a91a529586f56846ef3ba58255eb71c61e0f562d174ede8910b25`。
- 训练输入 SHA256：`ec8265523de02effca4dc71342ab5b5ff7bb14be52fe5188adcba3d63b0eef34`。
- 独立状态 `PASS_31_CONDITIONAL_PURE_COMPILES_NOT_ECONOMIC_ADMISSION`；所有压缩条目均再次逐文件读回验 hash。

31 窗、3,127 个候选证券月份通过的是训练准备，不是经济回测。第二份快照同样不宣称完整运行环境或所有旧清单的递归依赖闭包，也没有授权执行或证明策略收益改善。原第一份快照保持不变。尚在推进的逐日名义 OHLC 执行准备需另存后续检查点，不纳入这份已经冻结的 ZIP。

## 名义 OHLC 与精确成本 v4 复核后的第三份快照

`research_contracts/research_archive_20261026/old_window_execution_v4.zip` 已保存 31 窗 v4 输入、124 个证券标签的名义 OHLC 候选、逐日选源、争议报价、生命周期资料及两项独立复核。

- 977 个文件，原始合计 488,034,003 字节，ZIP 82,063,566 字节。
- ZIP SHA256：`840df9befe745b955998c7647737082b5c7aaf59744eef5c5155b8a967cb12f1`。
- 清单 SHA256：`872d507ba68af7f89ae32602ca779a4235487688c993b1c2b05fe42f44b987e3`。
- v4 训练 SHA256：`32d7293282553d4c98daa161641663c0082da8f85b8b638974863f1ea8e951d3`。
- OHLC 候选 SHA256：`3a0c0d3cc2b917a34c6f4328876dda50ee4cd8509af5c08e10fd86218729dfbf`。

全部条目读回 hash 通过，前两份 ZIP 保留。该快照可复用资料和数值校验结果，仍不是完整行动账本或新经济收益成绩；后续执行接口准备、真实暴露事件映射须分别验收。
