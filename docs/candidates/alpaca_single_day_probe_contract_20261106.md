# Alpaca 单日历史 SIP 探针运行合同

仅准备，尚未执行真实请求。等待用户确认注册/账号使用后，由用户在本机安全配置环境变量 APCA_API_KEY_ID、APCA_API_SECRET_KEY；不要在聊天发送密钥。脚本不检查现有密钥，不注册、不购买、不下单。

默认运行 `D:/python/python.exe -m scripts.research.alpaca_single_day_probe_20261106` 只打印固定 GET 计划，不读取环境凭证、不联网。明确增加 `--execute` 才读取这两个变量并请求一次。HTTP 重定向禁止，失败不自动重试、不记录请求 header 或错误正文，不跟进分页。

固定 AAPL，2022-01-03 14:30:00Z 至 20:59:59Z，1Min、SIP、raw、asof=2022-01-03、limit=1000、升序。权限是否允许该历史 SIP 请求尚未实测，成功与否均不改变费用/订阅；脚本没有任何购买接口。

成功行情原始字节、SHA256 与检查结果只存本地 tmp。检查重复、乱序、越界、非分钟时刻、非有限数、OHLC 包络、非负整数成交量、未结束分页。缺分钟如实报告且不补齐；accepted 仅表示已有行合格，full_regular_session 才表示全部 390 分钟存在。单日成功不代表长期覆盖、退市覆盖或策略收益成立。raw 表示请求未复权，实际单位仍须公司行动/其他来源核对。

官方接口合同：[Stock bars](https://docs.alpaca.markets/us/reference/stockbars)、[Market data FAQ](https://docs.alpaca.markets/us/v1.1/docs/market-data-faq)。密钥和私人账户资料不保存到仓库。

主线程复核：输出目录已存在时，在读取凭证或发送请求前拒绝；格式合格但缺分钟仍标记 INCOMPLETE_OR_INVALID，执行退出码非零。8 项离线测试通过，包括默认模式不读凭证/不联网、已有输出提前拒绝、畸形响应及行情校验。尚未执行真实网络探针，不据测试宣称已取得 SIP 权限。
