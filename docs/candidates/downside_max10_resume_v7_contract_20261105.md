# Downside max10 v7：GOOG/KDP股息配置续接

小入口沿v6的absence dispatcher及不可变v3核心，不复制经济runner、不修改旧冻结源。父late_v6完成541/646日、累计27次新选择、2131.3361789000337秒；六代选择来源2+3+3+13+4+2均保持原pins。

完整args重用、541行最新前缀先核再新搜索，原31次/10800秒及单月600秒预算累计继承。旧META/CEG/AZN/CTSH/LRCX ordinary与INSM absence证据继续保留，INSM不生成现金事件。

仅追加已独审GOOG/KDP配对材料；freeze前对父2026-02-27真实gate逐笔调用原股息和无行动准入函数，GOOG3/9及KDP3/27全部解除才READY，不以artifact数量替代准入。未经济运行。

准备入口：`python -m scripts.research.prepare_downside_max10_resume_v7_freeze_20261105 --artifact <配对路径>=<预期SHA>`，多artifact重复参数。

根审后执行：`python -m scripts.research.run_downside_account_candidate_20261105_v7 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v6 --output tmp/downside_max10_20261105_late_v7`。
