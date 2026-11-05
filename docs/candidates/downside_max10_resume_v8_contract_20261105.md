# Downside max10 v8：ASML最终股息会计续接

父late_v7完成563/646日、累计28次新选择、2260.365469100012秒。七代归属2+3+3+13+4+2+1，完整参数匹配复用；563行前缀核完才允许新搜索。仍最多31次/10800秒、每月600秒、十股；当前父链深度七，下次输出为第八代，不修改helper安全深度上限。

v8小入口复用不可变v3核心和v6 absence dispatcher，不复制账务。ASML paired artifact `tmp/asml_remaining_dividend_review_20261105/supplement.json` SHA 2fac5620c3e9f99cf3338219121e6239a6b19a62a82483238f71bafa539f65d7，税前Final USD 3.168450/2.137748、支付5/5及8/5。provider初值3.177不是舍入误差，必须按有证据Final映射，不与其盲等。

根已接受既有回溯经济会计口径：4/28公布的Final可以事后重述4/27除息权利，但**该段daily equity/DD不是当时可知净值**。不能只声明决策无前视而省略估值限制。未付股息不进入策略财富/现金/20%价格退出；付款日才成为可用现金，7月股息8/5在窗外保留应收。代码依据及严格as-of替代的缺项见 `asml_final_dividend_timing_20261105.md`，正式经济表必须保留此限定，并在有实际权利股数时报告影响规模。

freeze前真实注入所有paired后执行父3/31原gate，ASML4/27未映射消除才READY。仅准备测试与freeze，根执行经济：

`python -m scripts.research.run_downside_account_candidate_20261105_v8 --window 2024_2026 --parent-output tmp/downside_max10_20261105_late_v7 --output tmp/downside_max10_20261105_late_v8`
