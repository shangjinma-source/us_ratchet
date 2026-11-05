# SGEN动量实际暴露准入

独立模块 `momentum_sgen_admission_20261105.py`，私有证据 `tmp/momentum_sgen_action_20261105/supplement.json`，固定SHA256 `55e2a23e6e4069a742a82c191b480227abebc6c65c2f8a56f122711e545bb94e`。

实际六段为(3/31,4/28]、(4/28,5/31]、(5/31,6/30]、(6/30,7/3]、(10/31,11/30]、(11/30,12/29]。6/30后旧仓预期开盘退出，因此不是覆盖整个月。旧Q2资料不直接延伸；[Q3 SEC](https://www.sec.gov/Archives/edgar/data/1060736/000106073623000047/sgen-20230930.htm)融资现金流仅员工权益相关、并购仍待完成，补回溯7/3边界；[完成8-K](https://www.sec.gov/Archives/edgar/data/1060736/000119312523294938/d557257d8k.htm)与已保存Nasdaq确认12/14盘前每股229现金权利。

11月至12/13无其他行动是Q3、原协议限制分红/拆股条款与完成文件的有界联合推断，条款存在同意等例外，不能称官方穷尽认证。12/14并购显式登记，之后旧股终止，不伪称全段无行动。证据来自web工具官方正文观察及原本地Nasdaq，未把SEC拒绝页当原文。

`install(document)`追加原始现金merger到账务及provider行动并返回pins；`admit(gate, execution_events)`只处理这六段的SGEN缺流及唯一精确merger barrier，不改旧gate或其他股票。原recheck六gate均验证SGEN问题消失，结果 `gate_review.json`。缺执行事件、错误229金额、未核split三项负例均拒绝。

这些是潜在暴露门槛测试，不是收益回测。真实账务仍需正确终止股份/目标/风险，并分别使用已授权D0/D1/D5到账假设。不存在券商实际到账认证或无条件全域准入。
