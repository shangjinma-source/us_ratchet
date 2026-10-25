# 2020年末名义单位与Yahoo回填坐标核查

只读取现有本地响应，未发网络请求或矫正价格。24个差异全部可在已有Yahoo事件流中找到算术一致的因子，证据及响应hash见tmp/qqq_20201231_anchor_20261025/local_split_coordinate_review.json。但算术一致不等于真实普通拆股或准入。

- 原2017—2023响应足以解释TSLA、CPRT、DXCM、ISRG、GOOGL、GOOG、AMZN、PCAR、CSX、MCHP，以及EXC的供应商坐标因子。
- 原响应未含2024后事件，却将这些事件回填到2020价格；从现有2026缓存补得：MNST 2026-08-11 2:1（须与2023-03-28 2:1累乘）；CTAS 2024-09-12 4:1；NFLX 2025-11-17 10:1；BKNG 2026-04-06 25:1；AVGO 2024-07-15 10:1；KLAC 2026-06-12 10:1；LRCX 2024-10-03 10:1；NVDA 2024-06-10 10:1（须与2021-07-20 4:1累乘）；ORLY 2025-06-10 15:1；FAST 2025-05-22 2:1；SIRI 2024-09-10 1:10。
- EXC 2022-02-02 1402:1000、ILMN 2024-06-25 1028:1000、CMCSA 2026-01-05 1067:1000须走分拆/权益价格坐标分类，不能按供应商splits字段改变母股数量。CMCSA这一点已有本地annual_hon_cmcsa_conditional_scope合同明确说明。

实际待办：复用缓存事件与官方公告建立逐项映射；将回测结束后事件纳入价格单位还原证据但不作为回测期内持股行动；EXC在2021—2023期内须提供分拆子股权益/到账/估值路径；ILMN和CMCSA在窗口之后只影响源价格单位还原；SIRI反向拆股及同期公司重组要核身份不能仅按0.1。所有普通拆股候选也需官方语义确认。训练价格与执行名义价格分别声明，避免重复复权；不从SEC差值倒推后直接改价。

首批官方语义核对已落`official_split_semantics_batch1.json`：TSLA 2022-08-25 3:1、NVDA 2021-07-20 4:1及2024-06-10 10:1、Alphabet A/C 2022-07-18 20:1，共5个证券事件。区分分配日与首个拆股价格交易日，未把这些局部核实升级为全池准入。

依据：[Tesla公告](https://ir.tesla.com/press-release/tesla-announces-three-one-stock-split)、[NVIDIA 2021公告](https://nvidianews.nvidia.com/_gallery/download_pdf/60a7afd8ed6ae55e49ab1ea5/)与[后续10-K执行确认](https://www.sec.gov/Archives/edgar/data/1045810/000104581022000036/nvda-20220130.htm)、[NVIDIA 2024生效申报](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000144/nvda-20240607.htm)、[Alphabet股东材料](https://abc.xyz/assets/investor/static/pdf/2022_alphabet_proxy_statement.pdf)与[交易所两类别调整通知](https://www.miaxglobal.com/alert/2022/07/15/miax-exchange-group-options-markets-corporate-action-alert-alphabet-inc-1)。NVDA 2024事件仅用于恢复下载价格的坐标，不能在2021—2023账内提前增加股份。
