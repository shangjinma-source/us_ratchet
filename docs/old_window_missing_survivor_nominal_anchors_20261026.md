# 旧窗非当前幸存者：名义价格与身份复用证据

仅只读核验5只明确旧成员，不作经济回测、不自动签发路由准入。`tmp/old_window_nominal_anchor_20261026/review.json` 绑定旧 fixed_sources、各实际来源、2023年末QQQ官方表及原网页解析文本hash，逐票列出股数/市值、隐含名义价、校准系数与重叠差异。

|证券|2023-12-29名义价（USD，约）|可复用来源及结论|必须保留的障碍|
|---|---:|---|---|
|ANSS|362.88|旧archive factor1；新固定末年桥接与旧源499日重叠，约1cent高低价差已另审|2025-07-16末日，7/17现金+SNPS权益，不可当普通退市删掉|
|SPLK|152.35|旧桥接factor1；Chart源318日重叠OHLC精确一致，至2024-03-15|并购终止及现金到账须按专属官方证据，不延长平价|
|WBA|26.11|Zenodo factor1；Chart源77日重叠最大约0.005美元；后者覆盖6/26以后|CSV没有actionstream，不能把空事件数组当无股息证明|
|BIIB|258.77|旧源factor1；extended源126日重叠OHLC精确一致|新源无provider事件只支持有限声明，不等于官方完整无行动认证|
|ILMN|139.24|事件前名义factor257/250；extended与旧源126日OHLC精确一致|GRAL分拆为复杂行动，不能按1.028普通拆股处理|

五只重构2023年末名义价均与官方 `value/shares` 差小于0.00002美元。该一日锚加重叠可佐证价格单位/来源一致性，不能证明整个后续区间不存在公司行动。不同源报价差异保留，不按收益挑选每天报价，也不使用Adj Close。

ILMN 的现有 fixed_sources 已明确：2024-06-25 `COMPLEX_PRICE_COORDINATE_REQUIRES_TRAINING_POLICY_REVIEW`，`training_allowed=false`。这必须传到新compiler，不能因为坐标锚通过就丢掉。事件前 raw close 乘257/250恢复名义美元，事件后factor1；此倍率仅供应商价格坐标。实际权益是ILMN持有人获得独立GRAL（既有官方材料1股GRAL/6股ILMN），不是ILMN股数增加2.8%。跨该事件的训练信号如何保持经济一致仍需明确政策/权益实现，不能自行把名义价格缺口当损失、把供应商调整当完整总回报。已有文档及来源 `tmp/gral_official_membership_findings_20261014_v1/findings.json` 可复用；GRAL不继承母公司价格。

ANSS使用独立 `tmp/anss_terminal_bridge_20261026/review.json` 的实际最终对价199.91美元+0.3399SNPS，不用初始方案197+0.345。WBA和SPLK即便被指数删除，旧仓仍可能持有；现金分红/并购主账不能被成员删除替代。上述source与issuer/security ID沿用旧审核标识，未因同ticker引入前身。

本轮范围不包含全124/全当前池的行动认证。若代码agent路由到不同路径或hash，此证据不能自动套用，需重核重叠及校准。
