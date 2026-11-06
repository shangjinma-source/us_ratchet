# 同策略信号下现金更新与可信目标重建

候选 `frozen_target_builder_20261106.py` 提供 server-owned policy + quote_provider + account store 的纯隔离构造器。策略合同 SHA 为 policy canonical digest，含固定 epoch、weights、信号有效窗；rebuild 不接受客户端权重或目标。每次读取最新账户 revision 和服务端报价，生成独立文件内容digest、proposal digest，记录 previous_target_id，验证账户未变及 provider 全部约束后发布当前研究版本。

`tests/test_frozen_target_cash_refresh_20261106.py` 已通过：真实 account HTTP API 依次确认1000→3000→500，服务端调用 rebuild，再经正式 v3 preview HTTP API 分别取得可买10→30→5股。三版独立文件保留，前驱链正确，合同/epoch不变、无挂单、最终现金500。所有金额证券为合成，未写真实库、无8010重启。

这里服务端重建是测试中显式调用，不伪称生产现金按钮已有自动接线。正式接入仍需现金提交成功后的可信服务编排、进程锁/原子发布/重启恢复版本链、经济准入与源码pins；失败生成文件不被设为current，但本候选不实现生产清理或恢复。所有建议仍 executable=false / production_activated=false。不能把同信号更新股数理解为已经验证重新选股优于原规则。

重试修复：首次写文件后校验临时失败，current/versions不发布；同digest路径已存在时，仅允许非symlink普通文件且字节完全相同的复用，不覆盖任何不同内容。测试注入一次受控preview失败，随后篡改已存文件验证冲突拒绝且不覆盖，再还原后重试成功。已成功版本在同账户、同报价、同信号重复刷新时复用同版本并重新校验时效，不增加前驱链。当前测试通过；仍仅单进程候选，不宣称跨进程并发/重启恢复已实现。
