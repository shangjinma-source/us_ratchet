# 早七个月身份与原价路线补证

新增 `tmp/early_identity_bridge_20261026/review.json` 为 CCEP、DASH、MDB、ROP、LIN 建立 14 个精确决策日身份映射，证券 CUSIP 分别为 G25839104、25809K105、60937P106、776696106、G54950103。来源为 SEC 原始申报、MongoDB 发行人托管申报及 Nasdaq 转板公告，保存 web 工具文本与 SHA256；不是原 HTML。

CCEP 年报实际签署日 2024-03-15，晚于三个所需决策日。此项仅允许回溯核实证券身份，未将披露日提前，未输入未来财务值。其他签署日期也未冒充 SEC 接受时间。LIN 另记录 2023-03-01 新旧控股公司 1:1 换股和 2023-11-07 同 CUSIP 转板，不将相同 ticker 泛化为永久相同证券。

独立脚本 `tmp/early_identity_bridge_20261026/review_routes.py` 直接读取原始 CSV / Yahoo bytes，核对固定 hash 后复算 `early_raw_routes_v2.json`：103 条双源训练记录、18 个唯一 ticker/重叠组合的差额及 253 日向量均一致；WBA 重叠 77 日，其余为 126 日，最大原 close 差额均不超过 0.00001 美元。25 条五月末名义锚延展到六月末的严格后续因子及成本算术也通过。

证据 `tmp/early_identity_bridge_20261026/routes_review.json` 绑定输入 SHA256 `a265a2eb0ead01dcb223e0ac8fc25666050b82b8b53b60a8f536cabc9214f49c`。这只核查来源、向量和条件校准算术；延展不是独立六月末报价锚，provider 事件缺失仍不能等于官方证明无事件。未运行经济搜索、未修改冻结旧输入、未授权真实执行，也不声称收益或回撤已改善。
