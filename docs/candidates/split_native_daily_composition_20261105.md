# 新月原生目标的日建议组合

独立组合工厂复用原 daily composition 的账户快照、proposal绑定、信号时效、重试、现金及状态规则。执行桥改为保留实际 provider 子类审核的新桥；scoped preview 使用支持拆股账本的实现。零现金及买入数据缺失分支要求调用方显式提供对应桥，不隐式回退旧实现。

验证 `D:/python/python.exe -B -m unittest discover -s tests -p test_split_native_daily_composition_20261105.py -q`：1 项，1.191 秒，OK。

本次真实临时 monthly factory 搜索生成目标及持久化 proposal，受控完整分钟运输通过实际执行审核及限价算法，组合返回 READY、非空订单建议和 execution lineage。旧 revision 信号拒绝，测试账本不变、无外部网络调用。

限制：输入 signal 为显式合成控制信号，本测试不认证日行情 reader 的来源；mixed 分支使用不得触发的测试类，未据此宣称零现金或缺少买入数据通过。新桥及 reader 仍在并行完善，当前文件未挂载生产，也不代表经济收益改善。
