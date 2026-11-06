# ROA 月末行情输入复用核查

结论：已有采集和训练构造能力可复用，但不能直接把 `monthly_full_domain_capture` 的完整观测域当当前 ROA 98 股域，也不能把旧 V27 发布配置直接接入 ROA。应复用原始采集层、精确日期/身份/单位核验，再独立输出 ROA manifest 和月包；本次仅代码及本地样本审查，零网络、零账户写入。

## 实际已有证据

`tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json` 为 `CURRENT_EXPANDED_REBASED_MANIFEST_V1`：decision=2026-10-30、membership observation=2026-10-13、coordinate asof=2026-11-02。98 members/98 candidates 全为 READY_CONDITIONAL，253 日期；1144 个依赖当前均存在，总 59,310,328 bytes，最大单件 19,170,729 bytes（这里只核存在/大小，未重跑全部哈希）。`full_pit_verified` 和 `complete_corporate_actions_verified` 不应升级。

真实样本训练来源是 `normalized_v2/<ticker>/<ticker>.response.bin`，不是旧月目标。`training_review_v2/arguments.json` 记录了 capture_index、plan 和前 manifest 的精确绑定。`normalize_capture_v2.py` 保存原 retry receipt/hash 与 late_recovery 标记，重过 read_saved_quote；它是十月恢复专用脚本，硬编码 GILD/RKLB 和目录，不能当通用生产采集器。

## 可复用层及不可直接复用处

- `scripts/monthly_full_domain_capture.py`：默认零 HTTP preflight，收盘后才按每批最多5个已知SID采集；要求集合与完整 observed_symbols 完全相等，未定身份另存但不准入。故不能给它98子域、仍称完整当前纳指域。
- `scripts/monthly_experimental_domain_capture.py`：显式固定子域，身份/issuer 与旧输入一致；其 original validator 绑定原基期，不能随意换 latest manifest。
- `scripts/build_monthly_successor_plan.py`：已有固定域后继计划和 completed_previous 回放验证，允许相同域滚动，但依赖完成 receipt/旧 lineage。可作为只读验证器参考或可信调用；不是 ROA 激活入口。
- `scripts/prepare_monthly_captured_training.py::build`：可注入可信 Python `plan_validator`，无网络无选股；核 plan/index/每个 receipt/raw/decoded hash，收盘后采集时点、SID、USD等 reader 约束、253 日期、重叠旧收盘精确相等、split 集合与已审核 factors 相等。结果仍 conditional。
- `data/roa_monthly_selection.py::generate_month_selection`：已经直接消费上述 manifest 结构；要求全部候选身份/单位已审、完整253正价格及权威日历精确匹配，保持冻结 ROA+momentum 排序。之后走 ROA 独立 immutable package/registry prepare，绝不复用旧 V27 binding 激活。

## 最小 adapter 接口（建议，尚未实施）

`prepare_roa_training_capture(root, prior_manifest_ref, fixed_domain_ref, capture_plan_ref, capture_index_ref, session_calendar_ref, training_calendar_ref, now, output_directory)`

所有 ref 是服务端可信 `{path, sha256}`。先验证完成月末及同域SID/issuer，复用 `build(..., plan_validator=受控固定域验证器)`，再独立复核完整253训练日历。输出 create-only `manifest.json`、coverage、returned-action inventory、全部 source hashes；不输出账户目标/执行建议。若复用 successor lineage，必须真实回放其 completion；不能伪造 receipt。随后 `generate_month_selection` → `prepare_roa_monthly_package` → 独立配置注册准备，均保留旧版本。

## 必须补齐或核实的真实缺口

1. 11月末真实已收盘 capture/receipts 目前尚未发生，不能从十月样本平移日期。计划收盘时刻须用 `SCHEDULED_REGULAR_SESSIONS_V1`；新 dates-only training calendar 不能充当采集时钟。
2. 固定98域是否继续沿用必须显式绑定；若有成员/股类/SID变动，需新有效期身份审核，不按ticker继承，也不因缺数据删股。旧观测不是新的成员观察。
3. 新拆股/合并/更名及 provider 历史修订会被 overlap/factor门阻断。需逐事件已审核单位桥，不能四舍五入容差放行。`build` 对新 dividend 主要留存 inventory，**不完成到账日/金额/税及持股权益的经济行动准入**；这一层仍由账户证据链独立核。
4. `build` 会继承旧 training exclusion 与身份标志；adapter 不可自动将这些认证到新日期。ROA 当前98股全 READY，但未来新缺口必须明确阻断/待审。
5. 原包59MB目前低于 build 的128MB总量及32MB单件限制，继续滚动保留历史依赖可能增长；应测实际 closure，不扩大上限掩盖问题或删除必要证据。
6. 财务文件不由 capture 更新。当前规则按最近已完成季度截点读取同 accession/期间 NI、OCF、Assets，filed/end 严格早于截点，保留 CIK核验、缺失/冲突/过期原因；不能把新下载修订值当原时点值。11月末仍9/30截点；12月末升12/31截点时需重新实际读取及冻结合格财务版本，不可沿旧排名。`select(..., accepted={})` 仍仅 filed 层，不称精确 acceptance/PIT认证。
7. QQQ顺序完成收盘、市场状态、真实持仓公司行动和新鲜报价是独立 runtime 条件，单股票 manifest 完成不等于建议可执行。

可先实现该只读 adapter 并用已有10/30 capture 复现输入；未来月末实际采集后才允许构造新包。无需改原金融定时任务，也无需重新注册第三方账号。


## 已实现隔离 adapter 与真实回放

新增 `scripts/research/prepare_roa_fixed_domain_training.py`。六个显式引用均需 path/hash：prior_manifest、fixed_domain、capture_plan、capture_index、session_calendar、training_calendar。对原 original/successor 计划使用已有严格 validator（不替换为宽松新 validator），复用原 build；额外核域的 ticker/SID/issuer、月份结束、完整训练日历精确相等。输出目录 create-only。manifest 保持原 build 声明和字节，额外绑定证据留 receipt。

实际运行：

```powershell
D:/python/python.exe -m scripts.research.prepare_roa_fixed_domain_training --request tmp/roa_fixed_domain_training_replay_request_20261106.json --output tmp/roa_fixed_domain_training_replay_20261106
D:/python/python.exe -m unittest discover -s tests -p test_roa_fixed_domain_training.py
```

真实 10/30 回放约 1.5 秒完成，98 股；新 `manifest.json` 与原 training_scoped_publication 逐字节相同，SHA256 `a2d3e436ee1434772a49236ab5d8317eade2fb85db0e40076ae69b46079ebc6c`。保留原恢复采集时间/late receipt，不捏造当时可得性。PIT 与完整公司行动认证仍 false。2 个测试含日期/非月末/域/issuer/SID/source drift/重复输出不覆盖的负例通过。

边界：该入口接受现有严格 original/successor 固定域 lineage；它不凭新 manifest 自建合法 lineage，也不重新认证延长期间的身份有效期。未来 capture 仍须真实完成，变化必须另行审核。当前离线运行不调度、不更新 runtime registry、不修改账户。


### 连续月链补验

adapter 已额外写 `completion.json`，使用本次真实写出时刻、六个原 build 输入与实际 manifest/receipt 输出 SHA；不伪装10月末完成时间。新产物位于 `tmp/roa_fixed_domain_training_replay_v2_20261106`。原 `completed_previous` 未放宽，真实重放通过；completion SHA `ff14163110ab5bfc5df5a1d23289cabdc2468a769c5323171b6db4b57e2dca80`。

原 successor 日期读取器要求 NY offset，而现扩展 schedule 记录 UTC；原文件不变，在 v2 目录另存 `schedule_ny_equivalent.json`，仅 astimezone 转换已有时刻，每项断言同一瞬间，并新增原 schedule 哈希来源。用它调用原 `build_next_plan` 已生成 `tmp/roa_fixed_domain_next_december_plan_20261106`：decision 11/30、active 12/1，状态 SUCCESSOR_PLAN_CANDIDATE。没有未来 capture 或未来 manifest；账户/调度/注册均未写。验证摘要见 v2/successor_verification.json。
