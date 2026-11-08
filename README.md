# Ratchet 美股投资工作台

当前上线策略为 **ROA · 牛熊切换**。本仓库保留线上策略、账户服务、前端、月度维护与必要验证依赖。历史研究方案不代表当前生产建议；已移除的实验文件可从 Git 历史查阅。

## 日常使用

1. 启动本机服务，打开 http://127.0.0.1:8010/ 。
2. 在“今日建议”填写券商当前可用美元购买力，点击“更新现金并查看建议”。
3. 根据当次有效建议在券商手动操作，再录入真实成交或未成交委托；工具不向券商自动下单。
4. 卖出款到账、出入金或其他现金变化后，重新填写实际可用购买力。

OPEN建议支持盘中刷新至收盘退出时段之前，目标和限价保留开盘参考；最新报价、现金和委托校验仍生效。延迟执行不等于按回测开盘价成交。过期建议保留并明确标记为参考，不能视为有效挂单指令。K线BUY/SELL标记来自真实录入记录。

## 启动

已有部署环境可在 PowerShell / PyCharm 终端运行：

```powershell
Set-Location E:\Git\us_ratchet
D:/python/python.exe -m pip install -r requirements.txt
D:/python/python.exe -B -m api.server --host 127.0.0.1 --port 8010
```

`start_service.ps1`提供已有服务检测。服务已运行时不要重复启动。正式启动会校验完整依赖与本地部署配置，可能需要数分钟。

**GitHub源码不包含真实账户、密钥、行情缓存、私有部署配置或完整训练资料。** 新克隆不是可直接交易的已配置账户。保留本机`config/strategy_server_active.json`、其引用的`research_contracts`、账户数据库和证据；不要用空账户覆盖真实账户。不能通过关闭校验弥补缺失资料。

## 必要内容

| 路径 | 用途 |
|---|---|
| `api/`、`core/`、`data/` | 正式服务、账户账本、ROA信号与行情、部署校验 |
| `web/` | 工作台前端 |
| `scripts/` | 月度准备、版本衔接、维护与验收入口及其依赖 |
| `backtest/` | 当前运行链与月度准备仍引用的计算模块 |
| `tests/` | 当前策略、现金成交、图表与月度流程的必要回归及测试依赖 |
| `docs/` | 当前使用、部署、验收和精简范围说明 |

部分名称带旧版本号的模块仍被当前启动链显式引用或哈希绑定，因此保留；它们不是另行启用的交易策略。

## 验收与边界

- [本次盘中刷新及图表修复](docs/roa_intraday_refresh_delivery_20261107.md)
- [真实事件验收清单](docs/real_event_acceptance_checklist.md)
- [月度维护与衔接](docs/roa_monthly_handoff.md)
- [仓库精简范围](docs/repository_scope.md)

首次真实成交承接、现金保存、收盘跨日及此次显示修复已有记录。新版实际盘中与未来月底/新月仍需按真实事件验收。历史回测不保证未来收益或回撤上限；AI新闻分析不代表已经验证的增益策略。

## 回归验证

```powershell
python -B scripts/verify_roa_portable.py
node tests/strategy_roa_controller.cjs
node tests/strategy_roa_mount.cjs
```

便携验证不覆盖依赖本机训练证据的3组历史集成测试；具备完整资料时用`--with-private-fixtures`显式启用。部分保留的旧测试模块被当前夹具复用，其历史测试用例存在旧哈希/旧接口断言问题；不能将全目录discover视为已全部通过。
