# QSTK 历史退市样本核查

实际取得免费公开 PyPI 分发包，不安装、不执行其中代码，只读取指定 CSV 成员。

- 入口：https://pypi.org/pypi/QSTK/json
- 文件：https://files.pythonhosted.org/packages/8c/15/3298c4ee5d187a462883a7f80d7621a05e8b880a8234729e733769a3476f/QSTK-0.2.8.tar.gz
- HTTP 200，42364441 字节，SHA256 `3faffdc1eac070c804009e6ed0dda3a3f1c435e8ca67ca1eae80890915aa08c1`。
- 包含1014个CSV；三个指定缺口中找到 `QSTK-0.2.8/QSTK/QSData/Yahoo/GENZ.csv`，未找到 AMLN.csv 或 BEAS.csv。这不是证明后两者所有免费源都缺失。

## GENZ 实际字段核查

字段 Date/Open/High/Low/Close/Volume/Adj Close；2809条行情，2000-02-01至2011-04-08。2007—2009区间756行，实际首末2007-01-03与2009-12-31，全文件重复日期0，区间OHLC序关系异常0。

GENZ CSV SHA256 `bae6f62c70e6a1a358631d02ab4901e7ffae8f6ee088bfe3a3aab93f6840b3ac`。

仍未准入回测：独立交易日完整性、原价/复权单位、拆股与分红、证券身份及终止交易处理待核验。早期一行 Close=53.94、Adj Close=26.97 直接证明两列口径不相同，不能把 Adj Close 当成交价。本样本是旧存档，不需要当前Yahoo继续支持该退市证券。

原始包、目录清单、元数据、CSV与机器核查位于本地 `tmp/legacy_three_probe_20261025/`，不提交原始第三方数据。可使用目录清单对其它合法历史成员缺口做匹配，但不能用今天的存活股缩减历史分母。


## 复用同一包的剩余缺口扫描

无需新增网络下载，在指定21个标签中另找到 BMC、JAVA、LIFE、TLAB、JOY（JOY只作为JOYG潜在更名路线，身份未认证）。五者2007—2009均756个有限OHLCV行、区间OHLC序关系异常0、重复日期0。

| 标签 | 有限行情行 | 有限数据首日 | 有限数据末日 |
|---|---:|---|---|
| BMC | 3167 | 2000-02-01 | 2012-09-12 |
| JAVA | 1275 | 2005-01-03 | 2010-01-26 |
| LIFE | 3167 | 2000-02-01 | 2012-09-11 |
| TLAB | 3169 | 2000-02-01 | 2012-09-12 |
| JOY | 2828 | 2001-06-15 | 2012-09-11 |

JAVA文件含1738行日期标签延至2011-11-23，但后段是nan，不能将文件末日当行情覆盖末日。其Adj Close列还带末尾空格，转换时要显式记录规范化。当前不填补nan，不声称其代表收购后真实行情。

未找到AMLN、BEAS、CEPH、CKFR、FMCN、FWLT、JOYG、LEAP、MICC、NIHD、PPDI、SEPR、VMED、WCRX、XMSR、SUNW同名CSV。完整每文件原字节SHA、成员路径、字段、有限行统计位于 `tmp/legacy_three_probe_20261025/remaining_symbols_audit.json`。所有样本仍admitted=false，必须逐一审身份及公司行动，特别JAVA历史原价拆股口径与JOY/JOYG关系。


## 较早版本有界复查

预算最多2包，实际只下载1包：PyPI最早的0.2.0，发布日期2013-01-15。元数据不存在更早、收购前的发行版本；选择最早版本仅检验是否保留后来删除的旧存档，不声称发行日期早于目标公司收购。

0.2.0实际HTTP200，28585681字节，SHA256 `1c48a73128853cfc8f73aad8e349bb7a9c7179fad4d2e2b86801c4000f6706f0`，含608个CSV；剩余16个指定缺失标签均无匹配。未执行安装脚本、未全解压。无需盲扫第二个邻近版本，收束此路线。

来源地址、日期、目录及机器结果：`tmp/legacy_three_probe_20261025/v020_audit.json` 与 `v020_names.json`。该结果仅排除所查包，不证明其它公开归档不存在。
