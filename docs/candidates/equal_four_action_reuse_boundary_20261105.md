# A 四股对照：三类行动适配复用边界

只读代码与已有证据审查；未下载、未改生产、未运行回测或新增测试。结论：可在独立研究适配层解决大部分接线，不需新框架；ALXN仍有真实合同估值缺口，不能靠删除门禁解决。

## SMCI split_identity：小型接线

现成：`historical_dividend_next_open_book_research.py`已迁移真实持股、挂单数量/价格及旧身份终止；`continuous_guided_cost_monthly_provider.py`已迁移目标。`dynamic_risk_units.py:migrate_risk_splits`已按比例迁移peaks、last_closes、unit_ids和退出锁，拒绝后继历史碰撞。旧窗execution_inputs已含2024-10-01、1变10及双方SID/引用。

最小缺失：独立MonthlyExit研究adapter把已审核事件转成带event_id/old_unit_id/new_unit_id的risk schedule，在原月内调用既有迁移；当前adapter只接受同SID split。月界仍沿原重置，不能顺带引入B保峰。交易身份迁移不应造成重新准入、解除当月退出锁或重复拆股。

测试：复用`test_dynamic_risk_splits.py`和`test_historical_dividend_identity_independent_review_v1.py`已有夹具；新增当前实际runner集成：同月持仓/目标/峰值同时迁移、已退出锁保持、月界重置、后继碰撞失败无部分写入、真实次开盘数量与价格守恒。低复杂度研究接线，重点是独审覆盖而非新算法。

## AZN ADS转普通股：条件性接线

现成：`return_priority_ads_conversion.py:convert_dtc_ads`限定2ADS换1普通股、显式DTC_BENEFICIAL_INTERESTS，取消旧DAY订单、整股后继与不可交易零股分离；book/provider已有调用与目标向下取整（目标零头不是资产零头）。`dynamic_risk_units.py`可迁移价格峰值乘2及退出锁。

最小缺失：事件注入、显式账户模型、风险接线、奇数持股零股估值证据，以及pending权益下月度选股的可交易资产投影。既有`tmp/azn_next12_conditional_admission_20261014_v1.json`仅为行情坐标条件准入，不是实际DTC/汇丰交付证明；2026-02-02 Open保存190.4400与独立观察187.50的差异已注册，真实暴露需报告实际fill敏感性，不能换数据选赢家。

测试：复用`test_return_priority_ads_conversion.py`偶数守恒/奇数拒绝未定估值/重复转换/未来旧股买入拒绝，以及risk conversion夹具；增加同一实际runner风险锁和现金不增、目标floor与实际零股权利独立核算。可以条件研究模型完成，不可宣称券商实际到账。没有有效交付依据时不能默认把整股变可交易；可另用不可交易权益口径，但两对照必须一致。

## ALXN混合并购：现成权益引擎 + 有界缺口

现成：`return_priority_cash_stock_entitlements.py`转换旧股为现金应收、待交付整股、零股，绝不增加现金/可卖股；每日同日后继标价计总资产。`dynamic_switch_provider.py`的SELECT_TRADABLE_REPORT_TOTAL已经校验原账户/当天ledger一致、总权益=可交易+未到账，未到账不参与选股/限仓。可复用此投影逻辑，不能把动态策略本身引入A。`tests/test_dynamic_nontradable_capital.py`证明权益不能抬高50%仓位额度。

真实缺失：
- 已有`docs/alxn_merger_evidence_20261025.md`及schema_mapping确认2021-07-21开盘前生效、每ALXN现金60+2.1243AZN ADS。当前book mixed_today在交易后转换，须加审核过的BEFORE_OPEN相位，取消旧挂单、按事件前实际持仓计算资格；不能沿用收盘后模板。
- 零股合同是代理出售净款按比例、FLOOR_CENT；现估值器仅前收盘乘零股且CEIL_CENT。需有明确已知时点的净出售款输入类型，未知则保留未定权利并阻断完整收益认证，不能忽略零股或冒充精确估值。
- `continuous_guided_cost_monthly_provider.py`月度明确拒绝merger_entitlements/receivable，需要独立投影接口：只用cash+可交易持股选股，原ledger继续包含全部权益；不能把原账户简单清空权益字段后跳过对账。旧目标清除、已终止SID不得要求停牌后报价或重新选入；风险已终止身份退出追踪必须与非交易终止区分。
- 若权益长期未到账，协议已有后续ADS分红权，现普通股股息只按实际shares计，须应收权益股息或限定未覆盖时段并明确不完整。不能因不知道真实交付时间就把分红归零。
- 若留到2026，未交付ADS遇转换及同时分拆权益已有MIXED_SUCCESSOR_ACTION/ADS_WITH_MIXED_CAPITAL限制；只在真实暴露路径发生时扩展，不预建万能行动框架。

测试：事件前后权益守恒/旧订单取消、不得拿应收买股、净款零股floor与未知拒绝、已有AZN与待交付AZN不混同、同日后继标价缺失拒绝、跨月只用可交易资产且权益仍影响DD、权益后续分红不漏计、独立账务审计。复用`test_return_priority_cash_stock_entitlements.py`等；ALXN为中等有界研究适配，但缺净出售款/有效交付证据时不能许诺完整账本通过。

实施建议：先复用SMCI和AZN既有转换与risk接口；ALXN先按实际暴露核对已有材料和权益估值所需字段，若无法精确估值则保留明确阻塞。不得删除候选股票、强制事件前卖出或把未到账当到账来制造A完成。A与原V27均使用同一行动与可交易资产/总资产口径。
