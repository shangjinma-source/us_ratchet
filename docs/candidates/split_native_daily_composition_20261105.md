# 新月原生目标的日建议组合

独立组合工厂复用原 daily composition 的账户快照、proposal绑定、信号时效、重试、现金及状态规则。执行桥改为保留实际 provider 子类审核的新桥；scoped preview 使用支持拆股账本的实现。零现金及买入数据缺失分支要求调用方显式提供对应桥，不隐式回退旧实现。

验证 `D:/python/python.exe -B -m unittest discover -s tests -p test_split_native_daily_composition_20261105.py -q`：扩展后的 1 项综合测试，2.121 秒，OK。

本次真实临时 monthly factory 搜索生成目标及持久化 proposal，受控完整分钟运输通过实际执行审核及限价算法，组合返回 READY、非空订单建议和 execution lineage。旧 revision 信号拒绝，测试账本不变、无外部网络调用。

完整组合额外通过两种实际分支：仅将买入股票的受控原始行情改为缺少完整分钟序列，原规则拒绝后切到仅卖出；临时账本确认零现金后也仅生成卖出建议。两者均使用实际 native mixed bridge，返回非空 SELL 建议，没有 BUY；执行前后账本和原目标不变。前一种明确保留 NONCONTIGUOUS_OR_FUTURE_MINUTE 原因。零现金是测试前主动写入的合成事件，不是建议过程隐式改现金。

限制：输入 signal 为显式合成控制信号，本测试不认证日行情 reader 的来源；没有真实 HTTP 现金/成交或生产部署验收，也不代表经济收益改善。完整原始资料→reader→组合→HTTP 仍需继续接线。
