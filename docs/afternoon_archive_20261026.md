# 2026-10-26 下午完整基线增量归档

本地归档 `research_contracts/research_archive_20261026/afternoon_baseline_delta_v1.zip` 采用独占创建，所有条目完成实际解压读回并逐项核验长度及SHA256。原始文件及凌晨归档未删除或改写，ZIP不提交GitHub。

- 699个证据文件，原始共2,327,860,839字节；ZIP为312,587,237字节。
- ZIP SHA256：`2c8f156db40fdf135eeab2b6c81c2b1ff1c5e2a896697ebdaaeaf9bde90d2201`。
- `afternoon_baseline_delta_v1_manifest.json` SHA256：`4b3f6be51bf5b15102d1ae330f0a76701a5222abf1bb7daa1c6272e31a5a17b4`。
- 读回报告：`afternoon_baseline_delta_v1.readback.json`。

## 覆盖

包括`tmp/old_continuous_baseline_20261026_v1`至`v9`的全部本次运行文件，而非仅最终摘要；包括v9完整账本、31次选择、646个执行会话的独立审核以及完整通用报告。建包前已检查独立审核为`COMPLETE_DECLARED_INTERVAL_REVIEW_PASS`、报告为`COMPLETE_VERIFIED_ACCOUNT_REPORT`。

另包含`tmp/old_window_execution_resume_20261026_v1`、`tmp/old_window_exposed_actions_20261026_v1`、`tmp/qqq_month_end_warmup_20261026_v1`及这些JSON中source_hashes直接指向的新增证据。NVDA/MU官方HTML、WDC补证、条件缺事件字段审查、精确身份转换证据和QQQ预热原始响应保留。归档验证证明文件保存完整，不提升各来源原有证据等级。

未包含私人账户数据库，未备份或修改生产账户；未包含尚未产生的趋势候选运行结果，不能称为候选成果归档。

## 恢复依赖和边界

在独立空研究目录先校验并解压以下两个凌晨归档，再解压本增量；每包同名`EVIDENCE_MANIFEST.json`应分别保存，勿相互覆盖用于审计的清单。

1. `old_window_execution_v4.zip`：`840df9befe745b955998c7647737082b5c7aaf59744eef5c08e10fd86218729dfbf`。
2. `continuous_schema_delta_v2.zip`：`8ab6e66d60b111dee6e50021a7154fd1e703ad34ac9cae2c109346f7a61e5b50`。
3. 本次`afternoon_baseline_delta_v1.zip`。

只有同路径且同hash的凌晨文件被去重；具体依赖逐项列在本次清单`base_file_dependencies`。新包中若有同路径更新文件，以其本次固定hash为准，既有档案保留原版本。两基线账户仍为独立起始账户，不能拼接成2021—2026连续经济结果。

清单扫描覆盖本次目录及递归发现的source_hashes映射，不宣称全部隐含运行环境/外部依赖闭包已认证。Python环境未打包，恢复时需核验解释器、依赖和源码pins；不要将研究目录覆盖到生产账户。归档后新生成的代码或结果需另外保存，不追写本ZIP。
