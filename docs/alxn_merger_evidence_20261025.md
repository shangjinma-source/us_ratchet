# ALXN 2021 收购：官方条款与现有账本映射

[Nasdaq ECA2021-136](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2021-136) 确认最后交易日为 2021-07-20，盘后 20:00 后停牌；7/21 开盘前完成合并，7/22 是正式 suspension 日期，不能据此模拟 7/21 可交易。每股 ALXN 转为 60 美元现金与 2.1243 股 AZN ADS 的权益。ALXN CUSIP 015351109；[OCC 49014](https://infomemo.theocc.com/infomemos?number=49014) 给出 AZN ADS CUSIP 046353108。

[SEC 完成交割 8-K](https://www.sec.gov/Archives/edgar/data/899866/000110465921094624/tm2122733d25_8k.htm) 确认 First Effective Time 发生于 7/21，旧股权利终止并转换为对价请求权。[发行人完成公告](https://www.astrazeneca.com/media-centre/press-releases/2021/acquisition-of-alexion-completed.html) 明确新发行 ADS 于 7/22 09:30 EDT 开始交易。此处选择美元 ADS 路径，符合用户仅交易美股的要求；不将 ADS 当作伦敦普通股，也不把新 ADS 上市日当券商实际到账证明。

## 可直接复用的字段

`cash_stock_merger_events`：`event_id=ALXN_AZN_20210721`、`old_sid=ALXN`、`new_sid=AZN`、`effective_date=2021-07-21`、`cash_per_share='60'`、`new_shares_per_old_share='2.1243'`。开盘前生效证据已明确，证券主表绑定和实际生效前持仓由回放验证后确认 eligibility。旧 ALXN 挂单取消；不能将应收现金立刻当可用资金或将未交付 AZN 当可卖持仓。

## 零股的真实兼容缺口

[合并协议 §2.09](https://www.sec.gov/Archives/edgar/data/899866/000114036120028237/nc10017928x1_ex2-1.htm) 规定按同一持有人汇总后计算零股，不发行零碎 ADS；代理聚合出售，持有人按比例取得净款，并向下取整到美分。不是前日收盘价乘零股，也不是向上取整。

现有 `return_priority_cash_stock_entitlements.convert_cash_stock_entitlement` 可建立固定现金、整股和零股应收；但 `value_cash_stock_entitlements` 的 fractional_settlements 只支持前收盘价格及 CEIL_CENT，因此不能将现成 ANSS 零股模板用于 ALXN。若实际策略跨事件持仓且出现零股，需要最小 net-sale-proceeds 模式或明确未定值边界；未暴露则无需追查零股或到账日期。不得借此删除 ALXN 或强制提前卖出。

`cash_payment_date`、`stock_delivery_date` 和研究结算假设保持未定。历史假想账户不要求取得真实汇丰账单；后续选择可审查的统一研究到账假设，与官方事实分开，未到账权益计入总资产但不可用于选股。协议 §2.05(f) 还规定待交付 ADS 的后续分红权；仅若真实路径长期保留待交付权益，再处理该依赖。

证据和 JSON 模板：`tmp/alxn_economic_events_20261025/`。Nasdaq 原始 HTML 成功保存，SHA256 `96a794af9f81b4398343ec9b765895691ebc38d9f3ca9fb9aac32cb7cd7e5c99`；SEC/OCC 直接下载返回 403，条款来自网页工具核读，未冒充原始成功文件。未改框架、未注入经济回测、未提交。
