# 替代 Alpaca 注册依赖：Kibot 公开分钟样本

用户报告 Alpaca 注册验证码失败，明确要求换方案。该注册不再作为唯一推进入口，不重试验证码、不要求用户继续注册。

实际从[官方免费样本页](https://www.kibot.com/free-historical-intraday-data.html)提供的 IBM Unadjusted 链接下载，HTTP200，无个人账号或密钥。24,932条、64个交易日，实际文件范围2026-08-07 09:30至2026-11-05 15:59。CSV结构、正价格和OHLC包络、非负量检查无错误，时间有序且无重复。检查不包含独立行情交叉核对、全日缺分钟认证或公司行动单位认证。

本地原始文件：`tmp/kibot_public_probe_20261106/ibm_raw.response`；收据 `report.json`。SHA256为 `68b0ca6adaef18241c478497ba9479e3dae72d8ed1b1bf7a4212ab0745ed5660`。原始行情不推送GitHub。

供应商声明样本为常规交易时段、未复权版本；免费完整证券域和多年分钟历史未提供。因此不能称取得全市场数据、Ross盘前盘口数据或完整牛熊回测输入。

下一步限定为分钟入场机制的小样本对照可行性：先核事前EMA暖机、样本与原股票域差异，再决定是否运行。不能为得到结果改选事后赢家或扫描参数；若没有有效信号或只有工程读取价值，应如实报告，不用它批准上线。

## 逐会话与可知时间核查

以09:30至15:59的390分钟常规网格比较，46日完整、18日合计少28分钟，见本地 `session_coverage.json`。不补平线；供应商[完整性说明](https://www.kibot.com/quality/data-completeness.html)列举停牌、无成交或数据问题等原因，因此缺bar不自动等于数据错误，也不能推断该分钟没有触发价格。实际事件若跨缺口，单列其不确定性，不事后删除亏损交易。

[官方格式说明](https://www.kibot.com/file-format/data-format-reference.html)明确标准CSV时间是bar起点、默认美东时区。分钟close只能在该bar结束后用于信号。已按America/New_York处理夏令时，生成仅含真实观测行的 `normalized_observed_bars.json`，首条可知时间2026-08-07T13:31Z，末条2026-11-05T21:00Z；未把09:30bar最终高低收提前用于09:30成交。所有数值有限性检查通过。
