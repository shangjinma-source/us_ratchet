# B跨月持仓峰值：独立静态接线审阅

范围：只读 `cross_month_held_peak_adapter.py`、`cross_month_held_peak_runner.py`、`run_cross_month_held_peak_20261105.py`，对照原风险模块与真实账本调用。未修改运行文件，未另开经济实验。这不是完成账本独审或收益验收。

未发现应立即阻止本次固定运行的接线问题：

- wrapper相较原 `historical_dividend_frontier_research.py` 仅新增生命周期追踪，并在两处risk.apply传入实际position_epochs；原选择/订单生成/现金/股息/公司行动内核未改。
- 生命周期来自已完成daily_ledger及当前真实shares，正股数→0删除，后续正股数生成新ID；不是用目标或未成交清仓意图判断。原book禁止同一会话同SID多笔订单，因而当前模型不存在日内先清仓再买回而日终仍持仓的漏判路径。将来若放宽内核，此快照方法必须重新审查。
- 同月真正清仓不会清除原风险模块的exited锁。新生命周期只有新月初始化时不再携带旧峰值；没有新增同月买回许可。
- 新月连续持仓只改变峰值种子，随后使用原20%逻辑。部分卖出/追加买入仍同epoch；原峰值单位在同SID拆股时按原审查old/new迁移。换SID拆股仍会由原适配器SAME_ID_SPLIT_ONLY拒绝，不偷偷继承。
- 月末当天原核心先初始化新月状态，再以相同完成收盘价更新带旧峰值的状态；原核心明确允许同session且last_closes相同的幂等调用，无未来价或同收盘成交。
- launcher按本分支真实财富搜索，完整arguments相同时才用旧选择。A补充没有只放行gate：股息实际extend进document.dividend_events并传到底层账本。

仍须结果阶段核对：全窗完成标志、source hash保持、每日实际epoch与carried_peaks对应、独立资金/股数/权益核算；不得把已通过的小夹具或本静态审阅当成完整经济验证。未来恢复必须累计耗时和选择预算，不能重复从零启动。
