# 拆股三时点：反例与最小兼容候选

确认缺陷位置：`data/strategy_recorded_split_review_v1.py:60`将ledger `effective_at`纽约日期强等provider split日期。如果10/15收盘后发股、10/16开盘切换报价，正确8:1行动会因日期不同报`SPLIT_REVIEW_UNMATCHED_ACTION`。这是内容匹配的误拒绝；不是已证明生产发生错单。

不改旧ledger严格字段/哈希/回放语义。新侧车`SPLIT_THREE_CLOCK_CONTENT_V1`绑定action_id与原行动SHA256、证据source_references，分开`distribution_at`、`quote_unit_effective_at`、`broker_tradable_at`。本候选仅接受原effective_at确实表示distribution_at的明确情形；旧含义不清时拒绝，不自动解释/迁移。broker_confirmed_at仍是确认时间，不擅改为实际可交易时间。侧车缺失沿原流程，不推断下一日（更不能自然日加1）。

新增 `split_three_clock_review_20261105.py` 只在私有命名空间替换旧匹配器的一处日期选择，原源码SHA固定，账户replay、provider原文hash、比例、其他权益/未知行动拒绝均复用。返回新的内容检查状态，保留认证false、executable=false，并明确execution_blocked；它不是可直接消费的unit admission。

`test_split_three_clock_review_20261105.py`实际创建临时SQLite SplitStrategyAccountStore，先录2股买入，再录前晚8:1拆股，重读16股。旧匹配器因次日报价事件拒绝，新侧车仅内容匹配通过且前后账户完全相同。缺侧车/未来报价/错误action hash/缺证据/改发股时刻均拒绝。命令`D:/python/python.exe -m unittest discover -s tests -p test_split_three_clock_review_20261105.py -v`：2项通过（0.036s）。合成时点/原文夹具，不是真实SNDK或券商认证。

## 下游仍须分开处理，不能只替换match上线

- `docs/candidates/strategy_account_split_unit_review.py:65`训练边界、`:118`mark观察下界仍用effective_at；未来须用报价单位切换时点核价格坐标，不能允许前晚发行后、次日切价前的旧报价。
- `data/strategy_split_account_preview_v1.py:48/54`报价下界，`strategy_split_history_projection_v1.py:20`历史日界，`strategy_split_native_projection_v1.py:24`投影时间均仍共用effective_at。
- 挂单/开盘过滤以及broker可交易证据也需按各自时点独立核验；本轮没有更改这些入口，也没有在composition挂载新匹配器。原unit consumer不检查新status/blockers，故这些标记本身**不构成硬门槛**；当前生产保护来自没有挂载候选。

没有生产改动、真实账户操作、证据自动认证或迁移。下一步应只在来源/券商证据可用且下游时点合同一致时成组接线，不能重做已有拆股adapter。

## consumer负例复核

新增隔离 `split_unit_consumer_guard_20261105.py`，私有函数globals中接入硬检查，不改旧consumer或先前候选。`test_split_unit_consumer_guard_20261105.py`复用现有真实单位审核fixture，明确重现：原consumer把`execution_blocked=true`内容结果仍升级成`CONDITIONAL_CURRENT_UNITS_REVIEWED`；安全consumer对此抛`SPLIT_CONTENT_ONLY_NOT_CURRENT_UNIT_ADMISSION`。同一fixture同时证明无sidecar同日matcher返回与旧matcher完全一致、安全consumer正常旧路径亦完全一致。

执行`D:/python/python.exe -m unittest discover -s tests -p test_split_unit_consumer_guard_20261105.py -v`通过。该guard只建立不兼容接口的硬拒绝边界，不补足真实来源/券商认证，也不授权部署；本候选收束，不继续增加标记wrapper。
