# ROA 换月实际运行准备审计（2026-11-06）

结论：**月名单生成、验证和注册提案工具已经存在，但月末采集到正式采用的自动运行链尚未接通，不能称为只等月底。** 本轮只读检查，未改任务、账户、活动配置或生产源码。细节与当前源 SHA 留在本地 `tmp/roa_monthly_scheduling_audit_20261106.json`。

## 四层现状

| 层级 | 已具备 | 实际缺口 |
|---|---|---|
| 输入采集 | 11月已冻结输入；原有每日来源任务仍在 | 尚无已接调度的ROA月末完整证券域、253会话行情、当时已公开财务输入采集/manifest闭包。不能把QQQ每日更新当作全股票月末训练准备。 |
| 离线月包 | `scripts/research/prepare_roa_monthly_package.py::prepare` 调 `generate_month_selection`，检查月末已收盘、训练/执行日历一致，发布不可变bundle并复读loader | 需要外部提供可信manifest/request；当前训练日历479会话仅至2026-11-30，缺12/1导致12月包next-session检查失败。原脚本固定end，必须另版扩展而非覆盖已pin旧件。runtime日历71会话至12/31，包含12/1；此项不是runtime日历缺口。 |
| 注册发布 | `prepare_roa_monthly_registration.py::prepare` 核active/source/receipt，生成仅registry变更的配置、next_active、精确rollback | 明确只PREPARED_NOT_ACTIVATED，不切配置不重启。活动ROA `monthly_selections={}`，11月依靠原base，新月无批准包会WAIT；没有已接正式自动注册发布调用者。 |
| 调度 | ROA进程lifespan每60秒调用收盘恢复及QQQ日更新；原Windows金融任务保留 | 月包生成/注册不是该loop内容。扫描Windows所有任务动作（解码EncodedCommand仅查脚本名）未发现ROA月包、注册或生成入口；12项us_ratchet任务均为旧每日/旧月度/审计或研究任务。 |

## 原RealMonthly任务是否干扰ROA

`UsRatchet-RealMonthly-Update` 仍Ready，指向 `run_local_profiled_monthly_update_v1` → `run_rolling_profiled_monthly_update_v1` → `REAL_ACCOUNT_CONTINUOUS32_V1`，配置 `research_contracts/real_profiled_monthly_20261030_v2/launcher.json`，不是ROA月名单。

- 观察到11/6 18:14:14运行结果2。最近落盘finished仍为11/4，状态 `MISSED_PREPARATION_WINDOW`；不能拿旧receipt认定本次错误原因。
- 本轮只读逐一核98个launcher source pins，4个已不匹配：`api/strategy_account.py`、`data/strategy_account_archived_holding_charts.py`、`data/strategy_account_holding_charts.py`、`data/strategy_bounded_source_gate_v1.py`。launcher在创建运行目录/执行scheduled_run之前先gate，现状不能进入旧月度采用。没有实际重跑任务。
- 若将来其旧pins重新核准并成功：`ProfiledMonthlyReleaseActivation.adopt` 只读取真实账户并短时 `BEGIN IMMEDIATE` 锁定核版本，最终rollback账户连接；写的是 `profiled_active_monthly_releases_v1.sqlite3` 的旧profile发布记录，不append账户事件、不创建订单、不创建月目标、不替换 `config/strategy_server_active.json`，也不写ROA lifecycle或月registry。
- 因此当前失败没有发现直接改真实现金/持股或切掉ROA的路径。但旧发布/估值基础服务仍嵌在ROA基础链，不能笼统称旧任务任何情况下完全无影响；成功路径的锁竞争、旧数据采用应在未来迁移时单独核验。本轮不禁用、不改任何原任务。

## 最小可执行接入顺序

1. 日期扩展由delivery独立处理：复用已核官方2026日历生成新版训练日期，覆盖12/1执行会话；保留旧训练artifact及SHA。测试缺下一日、重复/漏训练会话和日历冲突仍拒绝。
2. 增加独立ROA月末协调器，输入采用服务器配置和时钟：月末收盘前WAIT；收盘后验证实际行情/财务manifest完整性，再调用 `prepare(...,create=True)`。数据不齐明确缺口，不复用旧月名单，不编未来月包。
3. 月包复读通过后调用注册prepare；以预期active SHA、完整启动gate和真实账户前后不变完成受控发布。已有月包幂等识别，失败保留receipt且不重复采集/覆盖。
4. 用隔离历史已完成月末演练采集闭包→包→注册→运行时采用；加停机补跑、资料不齐、源变化和并发发布反例。随后单独安装ROA调度；旧金融任务保留，是否替换另做逐项迁移。
5. 真正11月底数据及12月实际换仓仍需届时验收，但上述协调器/调度/日期覆盖是现在能完成的开发项，不能归类为只等待时间。

## 后续离线协调器（尚未安装/激活）

`scripts/research/coordinate_roa_monthly_offline.py::coordinate(root,request,now)` 已串接现有package和registration。request为服务器持有JSON：`active={path,sha256}`、`decision_date`、`package={manifest,session_calendar,training_calendar,expected_month,output_directory}`（各输入为path+sha256）、`output_directory`。内部包输出自动置于唯一attempt下，避免覆盖既有产物。

- 月末前WAIT；输入缺失列出missing，明确acquisition_implemented=false。
- 同输出目录独占running.lock；异常退出遗留锁需明确核对，不凭时间偷锁。
- 每次失败保留独立attempt及failure；成功complete保存产物SHA闭包，重复请求复验当前active/code、bundle和loader后返回同提案，不重复生成。
- request变更或产物篡改拒绝；active并发变化不发布complete；输出仅PREPARED_REGISTRATION_NOT_ACTIVATED，不写账户、不改任务、不切生产。
- `tests/test_roa_monthly_offline_coordinator.py` 7项通过：完整包/loader/注册链、WAIT/缺输入、锁、重入并发、失败保留重试、active变化（包括耗时产物hash期间变化）。复用已有临时历史月末fixture，仅选股返回值替身；没有为演练复制真实350MB输入，也不把fixture声称真实选股验收。
- root已另核新版训练日期至12/31及真实10/30包dryrun通过。本协调器仍需外部真实资料采集manifest，调度和受控激活是下一层，不因本实现宣称自动换月已全通。

## 受控发布前校验入口（未激活）

新增 `scripts/research/prepare_roa_monthly_publication.py::prepare_publication(root,active,registration,output_directory)`；active和registration均必须path+SHA。它复核注册receipt、原始selection一致性、不可变运行包及所有既有月包，严格只允许`monthly_selections`追加一个月；经济contract/epoch/account、执行窗口、源pins及base链任何其他字段变化均拒绝。

完整启动校验直接复用 `api/strategy_server_mount_v9` 使用的 `build_unified_server_preparation_v34`，对当前与拟发布配置分别构造并执行`validate_code()`，不启动lifespan、不发HTTP、不启动服务。通过后保存当前active原字节rollback、next_active及来源绑定报告；全过程复查active及已读源。报告仍是`VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED`，正式切换前必须重新CAS与验证来源，不能凭旧receipt跳过。

`tests/test_roa_monthly_publication.py` 5项隔离通过：精确追加和两次gate调用、非月字段改变、额外月份、gate内active变化、正式gate失败。测试复用临时registration/loader真实实现；完整V34 builder在小fixture中为边界替身，因此不声称已完成某个真实新月的全链preflight。此轮没有复制巨大月包或触碰生产。

发布校验补强：递归收集当前及提案的全部`base_*`配置与每层声明`source_pins`，拒绝循环/同路径异SHA，将此声明闭包纳入receipt，并在写出validated前再次调用两套正式`validate_code`和全部已收集SHA复核。测试现7项通过，含完整builder返回后写next_active期间源码被改，拒绝输出validated。receipt明确声明其source_hashes不是所有运行数据的全递归闭包；正式switch必须重新构造完整V34并validate，再做active CAS，不能只凭receipt哈希批准。

副作用边界：不进入应用lifespan，不启动ROA60秒维护；ROA lifecycle/recovery构造器仅持有路径/锁，实际文件写发生在_save/_write；cash classification构造不调用显式initialize。未对全部历代base构造器证明“任何辅助文件都只读”，故结果filesystem_read_only=false，account_writes=false仅指本入口不append账本事件。没有执行真实生产构造器，本次仍是隔离fixture校验。
