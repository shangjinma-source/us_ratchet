# ROA 十二月计划研究来源归档

复用已有 `publish_roa_immutable_inputs.publish/verify` 的显式哈希复制及全量验证；新增 `scripts/research/archive_roa_training_sources.py` 提供默认 check、显式 archive 和缺失文件限定 restore。来源清单必须外部可信 SHA，publication 同样需可信 SHA。保留所有原文件相对路径与字节，不改 manifest。

实际清单来自真实 successor.prepare 和10/30 adapter回放的文件读取闭包，再加两份明确 request：1166 项，377 项在 tmp。不是扫描整个 tmp，也不是盲递归所有历史JSON。清单 `tmp/roa_december_required_sources_20261106.json` SHA `175e43f9bb80eef6978e4b263b4af6bcc4eb439652eca2f47b3e0073c11e5d7e`。

真实归档 `data/strategy_archives/roa_december_training_20261106_v1` 已创建：包括清单本身共1167文件/61,226,231 bytes。目录由已有gitignore规则忽略，不进GitHub。publication SHA `30e32f5381aac34ad1f0d3542542131c283012e0e1a11aafd893de1788ec6feb`。已全量SHA验证，默认check返回missing=[]、restored=0。

原successor validator已实际从归档独占读取1157个文件字节，通过11/30计划preflight；为保留completion中绝对路径绑定，使用原logicalroot，仅将read_bytes指向归档，原stat路径仍存在。证据 `tmp/roa_december_archive_replay_20261106.json`。未删除真实tmp，不声称完全脱离原路径或能任意迁移新root。

恢复先验证完整归档及所有现存源：任何不同字节拒绝整批覆盖；只对缺失文件以xb写入，最后全量复核。损坏/部分归档拒绝；中断可能留下已经正确恢复的部分文件，下次check明确显示剩余，不声称跨文件事务原子。旧路径依赖仍在，只增加可校验恢复备份。

```powershell
D:/python/python.exe -m scripts.research.archive_roa_training_sources --directory data/strategy_archives/roa_december_training_20261106_v1 --publication-sha256 30e32f5381aac34ad1f0d3542542131c283012e0e1a11aafd893de1788ec6feb
D:/python/python.exe -m unittest discover -s tests -p test_roa_training_source_archive.py
```

2项测试包含缺失恢复、现有差异不覆盖、路径遍历/账户敏感路径拒绝、损坏/缺件归档不恢复。研究归档不包含活动生产配置、账户、密钥或浏览器；代码/发布配置另由Git及私有发布资料保留。未来capture尚未产生，不属于本次快照；源变化须另出新清单/归档，不自动修改批准SHA。
