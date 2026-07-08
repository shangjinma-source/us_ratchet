# us_ratchet

美股科技篮子棘轮策略工具：支持历史回测、NAV-DD 面板、实盘状态、今日执行建议、战术挂单研究、券商流水导入和前端仪表盘。

## Quick Start

```powershell
pip install -r requirements.txt
uvicorn api.server:app --host 127.0.0.1 --port 8010
```

Then open `http://127.0.0.1:8010/`.

## Research Commands

```powershell
# 候选美股池诊断/推荐篮子，不改 config/state
python scripts\universe_research.py --tickers "NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM,MSFT,GOOG,AAPL,SNPS,CDNS" --monthly 3000

# 自选分组组合 A/B，对标 012922；默认同时验证 top4/top6/top8 精简篮子
python scripts\target_basket_ab.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --include-voltarget

# 镜像 012922 最新披露 US 持仓子集，扫描 core/W；research only
python scripts\fund_mirror_research.py --fund 012922 --monthly 3000 --top-n 10 --safe-weights "0,0.14,0.26,0.30,0.34,0.36" --core-ratios "0.90,0.95"

# 按 012922 历史季度披露做点时 US 持仓镜像；避免 latest-holdings hindsight
python scripts\fund_quarterly_mirror_research.py --fund 012922 --monthly 3000 --top-ns "4,6,8" --weight-modes "fund_weight,capped_fund_weight,score_risk"

# 战术固定限价 A/B：同时输出 vs关闭战术单 与 vs当前实盘战术配置
python scripts\tactical_overlay_ab.py --monthly 3000 --local-only

# 点时动态篮子 walk-forward：每个起点只用起点前历史选篮子，默认含 top4/top6/top8
python scripts\preference_walkforward.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --safe-weights "0,0.26"

# 低频主动重选/调仓成本回放：主动卖出重建仅用于研究，不接入今日建议
python scripts\preference_rebalance.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --safe-weights "0,0.26" --rebalance-months "6,12" --trade-cost-bps 10

# 动态候选篮子实盘准入预检：同时对照 012922 与当前写死配置，不写 config/state
python scripts\live_candidate_gate.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000 --include-voltarget
```

Research scripts are read-only: they do not write `config.yaml`, `data/state.json`, or today's executable advice.

## Dashboard / API Notes

- `/api/state` includes `execution`, `explanation`, and `config_health`; research candidates do not feed this endpoint.
- `/api/state.account_readiness` is read-only account/cash readiness context. It reminds the UI that broker holdings and broker available cash must be confirmed before producing share-count buy plans.
- `/api/research_candidates?compute=false` returns the fast read-only candidate/watch summary. Use `compute=true` to recompute light sources, and add `include_heavy=true` only when you intentionally want heavier point-in-time and fund-mirror research.
- `/api/tactical_quality` is read-only tactical-fill quality feedback: filled-price discounts, same-day open/low/close comparison, 20/60 trading-day follow-up, repeat-fill intervals, and current unfilled limit rough opportunity cost.
- The dashboard is split into Today, Buy Plan, Account/Cash, Research Center, and Guide pages. Detailed A/B tables are behind the Research Center toggle.

## Notes

Runtime portfolio state and market cache files are intentionally ignored by Git:

- `data/state.json`
- `data/state.json.bak`
- `data/audit.jsonl`
- `data/cache/*.csv`
- `data/cache/*.tmp`
