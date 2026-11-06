# ROA 月包配置发布准备

入口：`python -m scripts.research.prepare_roa_monthly_registration`，提供 `--active-path`、`--active-sha256`、`--receipt-path`、`--receipt-sha256`、`--output-directory`。

只消费已生成且验证的月包。检查当前 active/config SHA、V34、当前代码 source_pins、base_v33、正式月 loader、原始 selection 与冻结 runtime 的一致性；拒绝覆盖已注册月份、路径越界及已有输出目录。输出新 deploy-v34.json、next_active.json、原字节 rollback_active.json 和 preparation.json。除 monthly_selections 新增一月外，配置字段保持不变。

本入口仅准备文件，不更换 active、不重启、不修改账户。后续既有发布流程必须再次比较 preparation 中 expected_active SHA 并验证源文件，才能切换；它不是自动发布或对未来真实数据的认证。真实新月市场信号、行情、成交承接仍分别验收。未来发布沿现有用户授权执行，不增加额外人工审批要求。

测试：`D:/python/python.exe -m unittest discover -s tests -p test_roa_monthly_registration.py -q`，仅临时合成文件，无本机大数据依赖。

准备阶段实核配置列出的 source_pins，但不替代正式 V34 启动门对 SOURCES 完整集合及全部基础配置的校验；发布仍须运行完整正式 gate。准备期间源或 active 改变会拒绝成功收据；可能留下未完成输出目录，不能发布这类目录。rollback 始终是起始已验证 active 原字节。
