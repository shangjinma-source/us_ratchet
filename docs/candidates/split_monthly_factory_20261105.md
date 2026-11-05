# V27 拆股后月度选择：隔离工厂实现

已实现完整月度 **runtime→真实原 continuous32 select→target SQLite→SavedFrontierMonthlyView** 单元，未接生产 rolling router / ready-release adoption。没有改选股参数、12个21日情景、cap50 proposal、退出策略，也没有修改旧训练文件或旧receipt来冒充新批准。

文件：`split_monthly_factory_20261105.py`、静态小改的`split_monthly_unit_review_20261105.py`；测试 `tests/test_split_monthly_factory_20261105.py`。

## 实际验证

2026-11-05执行 `D:/python/python.exe -m unittest test_split_monthly_factory_20261105.Tests -v`：2项综合测试、3.586秒PASS。正例分别为拆股发生在253日训练之前、在区间内且raw未调整、在区间内且raw已拆股调整。所有正例都执行原连续32真实搜索并持久化target/proposal；同请求幂等；临时账户再确认现金后重新配置生成新decision并绑定新revision。负例拒绝未知basis和重复/遗漏单位调整。

根线程最终源码独立命令：`D:/python/python.exe -m unittest discover -s tests -p test_split_monthly_factory_20261105.py -q`，2项3.599秒全部通过，退出0。

训练审核调用既有`normalize_monthly_raw`取得253个精确当前单位收盘价，与`compile_saved_training(...).compiled.window.candidates[].training_close`逐项Fraction相等，且决策日价格相等。原compiler已有`RESTORED_PARENT_PRICE_ONLY`、price_coordinate_factors及true_share_events，故无需换算法；AS_TRADED需真实share ratio，已调整raw先恢复名义坐标再由share ratio抵消，normalizer独立防二次除。

原始bytes/hash不变；review独立外部SHA绑定manifest、原actionhash、timinghash、完整日期与rawhash。新代码必须同时出现在明确approval_pins及新配置runtime_pins，并核本地及执行源码；旧源码pins仍保留，不解释成旧批准已涵盖新函数。review与源码gate不能代替发行人/供应商/券商真实性审核。

原provider从training-close/持仓成交时点抓行动会漏掉更早split。新工厂仅在单次临时provider view中把真实行动请求start扩大至已绑定Q；原request/receipt由原capture真实生成，未追改观察日期。当前只支持单一已记录split的三时点审核；多行动链明确拒绝，尚未伪称支持。

## 尚未完成

本轮测试生成INITIAL以及同月EXPLICIT_RECONFIGURE，未把它标为真正两个ready release之间的MONTHLY_SELECTION验收。生产`ProfiledRollingMonthlyRuntimeRouter` resolver/identity仍旧replay；`ProfiledMonthlyReleaseActivation`旧receipt重放用旧apply_event；`strategy_account_ready_release`底层review仍旧版本。这些必须成组接新factory，历史receipt继续按其历史账本前缀及旧代码语义重放，新ready receipt独立绑定新approval/source closure。

真实当前SNDK未来split落入下一月253日窗口已在算法接口上可表达且区间内两basis合成实例通过；仍需真实供应商口径review及新月训练资料，不可拿合成源当认证。没有操作真实账户、生产配置、服务、金融定时任务或经济回测。
