# 动量六个拆股事件映射交付

固定五个同SID拆股：早窗NVDA2021-07-20 4:1、MNST2023-03-28 2:1；后窗NVDA2024-06-10 10:1、AVGO2024-07-15 10:1、CTAS2024-09-12 4:1。另SMCI2024-10-01 10:1跨SID复用assembled原事件。

`docs/candidates/momentum_split_admission_20261105.py::FixedSplitAdmission`：初始化验证冻结mapping及全部来源hash；`install(document,window)`返回独立副本，只对同SID缺失事件成对加入`assembled.actions/provider_actions`。已有SMCI事件要求原样存在。重复、同键冲突、两数组不一致均拒绝。`admit(gate,document,window)`只认固定provider观察逐字段相等，未知/篡改事件保留阻断；不用人造1股清仓准入。

六事件前一会话与生效日共48个OHLC字段，均核对「冻结raw × 已审核未来拆股坐标因子 = 现assembled名义OHLC」。早窗NVDA有窗口外2024再拆10倍、MNST有2026再拆2倍，使用原source_reviews已明确的坐标事件，避免只读截短raw事件导致漏还原。没有修改或再次缩放任何OHLC。

此层仅动作证据与执行事件配对。实际股份、目标、峰值/退出锁由已建原账务及独立`momentum_action_bridge_20261105.py`承担；本轮没有更改该桥，没有整窗经济回测。SGEN现金并购仍未被本层放行。

测试 `test_momentum_split_admission_20261105.py`：3项，7.627秒通过。真实两窗document接线幂等、原输入/价格不变；真实67月gate中的六类固定事件精确匹配；未知ratio、缺provider对、重复动作和改名义价拒绝，SGEN保留阻断。

材料：`tmp/momentum_split_mapping_20261105/mapping.json`，SHA `6dc917e61e9b2d74e0e104659f3f9627800a6a79d24c631215d05f0900d0f1f0`；MNST官方解析事实单独保存，不冒充HTTP原文。所有来源仍为既定条件性数据，不因此新增PIT/OOS认证。
