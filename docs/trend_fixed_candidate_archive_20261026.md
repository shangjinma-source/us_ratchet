# 固定10月趋势候选归档

两窗口完整候选均已独立验收。后窗年化降低，候选拒绝，不修改生产或继续阈值搜索。归档保存失败结果及可复核证据，不代表策略被采用。

本地文件：`research_contracts/research_archive_20261026/trend_fixed_candidate_v1.zip`，独占创建，227个文件、原始726,309,712字节、压缩87,697,496字节；全部条目已实际读回核对hash和长度。

- ZIP SHA256：`eff1e66654588c274927dba82f405c64e0b2e42f33159a8e56ecffce2c6c5ee2`。
- `trend_fixed_candidate_v1_manifest.json` SHA256：`aee1fdad7ad639f6b87e3e4da762effb5cc125acb3610e5273c65495cafc54f9`。
- 读回报告：`trend_fixed_candidate_v1.readback.json`。

覆盖两个`tmp/trend_2021_2023_20261026_v1`、`tmp/trend_2024_2026_20261026_v1`完整目录，`tmp/trend_2024_2026_baseline_prefix_reuse_20261026_v1`、`tmp/build_long_market_trend_result.py`、候选runner/独立reviewer/规则模块及新增直接source_hashes依赖。建包前核实两窗均有`independent_review.json`且状态为`COMPLETE_DECLARED_INTERVAL_REVIEW_PASS`，并有`generic_complete_report_v1.json`且状态为`COMPLETE_VERIFIED_ACCOUNT_REPORT`。

恢复需在独立研究目录校验并解压下列依赖，然后解压本包；每包同名清单单独保留，不覆盖审计副本。文件去重仅在同路径同hash时进行，依赖逐项列在本包清单的`base_file_dependencies`。

| 依赖归档 | SHA256 |
| --- | --- |
| `v27_2021_2023_verified.zip` | `4b73ac714a11273b1f1f0bf2c791071f15d8fb7a964e4a66e5f653b5caef59ed` |
| `old_window_execution_v4.zip` | `840df9befe745b955998c7647737082b5c7aaf59744eef5c08e10fd86218729dfbf` |
| `continuous_schema_delta_v2.zip` | `8ab6e66d60b111dee6e50021a7154fd1e703ad34ac9cae2c109346f7a61e5b50` |
| `afternoon_baseline_delta_v1.zip` | `2c8f156db40fdf135eeab2b6c81c2b1ff1c5e2a896697ebdaaeaf9bde90d2201` |

不包含私人账户数据库，不提交ZIP，不恢复到生产账户。Python环境及未显式记录的依赖闭包未认证；公开源码加本地档案也不等于独立样本外证明。两账户独立起始，不得拼接为单条2021—2026连续收益。归档不提高条件历史数据的认证等级。
