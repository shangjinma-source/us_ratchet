# 三时点拆股补采候选：两代真实采集闭环

仅隔离研究候选，未挂载生产，未认证券商实际到账或provider价格basis。

复用已提交补采模块的 `prepare_request` 和 `review_generation`；新 `review_pair` 将真实action及完整timing/calendar束纳入trusted descriptor，旧代按其本身receipt、basis、时钟审核，新代同样独立审核。后验历史投影使用三时点 `quote_bar_boundary_at`，不向旧receipt插入未来事件、不改旧原文。

旧代允许 D < parent capture < Q：本夹具D为10/20夜间，parent为10/21盘中，Q为10/22开盘。要求旧代明确old_unit、basis_asof<Q且所有完成会话早于第一完整新单位会话，不能以分发D强行断开报价坐标。当前实现仍是有界单行动旧单位parent路径，不宣称支持任意多代行动。

`apply_capture_pair` 从实际只读prepared SQLite读取原transition与timing，验证账户祖先、原archive提案、实际当前风险和固定日历重新计算补采request；逐证券原raw、单位review、receipt接收时间及max汇总均绑定现reader材料，然后调用真正三时点daily reader推进隔离风险。账户前后快照不变；不能凭fetch成功自动构造信任。

验证命令：`D:/python/python.exe -m unittest discover -s tests -p test_split_three_clock_supplement_20261105.py -v`

最终session93513退出0：3项综合测试，41.344秒PASS。覆盖AS_TRADED与已拆股调整两种表示、真实capture_supplement及gzip.compress响应/Content-Encoding:gzip的受控transport、不同SID接收时间、旧代不变、真实风险退出保留；覆盖重叠价格不一致、缺会话、未知basis、额外行动、倒置receipt/floor和采集中账户变化拒绝。网络被禁止，行情与时点为明确合成夹具，未mock交易建议或风险计算。

为不影响另一agent已冻结测试，新test只静态复用三时点fixture建库方法并增加distribution_at入口，未修改原fixture、原候选或生产。最初仅D前parent的测试通过不作为最终结论，最终以D后Q前路径为准。

文件SHA256：

- docs/candidates/split_three_clock_supplement_20261105.py: `6246714eb8ada93fd382acfc3318d3c7a52e7d8a7745c12b194787f48979b9f8`
- tests/test_split_three_clock_supplement_20261105.py: `c8159a1e3bca1bb8f9c4746e458b00ba96ed249e6720ec9ca9d16b78bc13928b`

根线程将派生会话日期明确转换为纽约时区，随后对最终源码独立运行同一测试：session89946自然退出0，3项综合测试33.718秒全部通过。未写真实账户或改变生产策略。
