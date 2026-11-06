"""Read-only accounting decomposition; not a counterfactual strategy backtest."""
from pathlib import Path
import json,hashlib
from fractions import Fraction as F
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
R=ROOT/'tmp/cross_sectional_momentum_static_20261105/result.json';roster=json.loads(R.read_text())['rows'];pins={str(R.relative_to(ROOT)):hashlib.sha256(R.read_bytes()).hexdigest()}
paths={'early':{'v27':'recent_continuous_baseline_20261026_v7','momentum':'momentum_account_early_20261105_v1/D0','inverse':'inverse_vol_momentum_20261106_2021_2023'},'late':{'v27':'old_continuous_baseline_20261026_v9','momentum':'momentum_account_late_20261105_v1/D0','inverse':'inverse_vol_momentum_20261106_2024_2026'}}
out={}
for window,groups in paths.items():
 out[window]={}
 for name,folder in groups.items():
  p=ROOT/'tmp'/folder/'book.json';raw=p.read_bytes();b=json.loads(raw);b=loads(raw.decode()) if b.get('encoding') else b;assert b['status']=='COMPLETE';pins[str(p.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();rows=b['daily_ledger'];stats={};prior=F(20000)
  for r in rows:
   gate=max((x for x in roster if x['decision_date']<r['date']),key=lambda x:x['decision_date'])['gate']['risk_on'];g='ON' if gate else 'OFF';year=r['date'][:4]
   for key in (g,year,'ALL'):
    s=stats.setdefault(key,dict(days=0,exposure_sum=F(0),cash_sum=F(0),equity_delta=F(0),zero_stock_days=0));s['days']+=1;s['exposure_sum']+=F(r['stock_value'])/F(r['equity']);s['cash_sum']+=F(r['cash'])/F(r['equity']);s['equity_delta']+=F(r['equity'])-prior;s['zero_stock_days']+=F(r['stock_value'])==0
   prior=F(r['equity'])
  out[window][name]={k:dict(days=s['days'],mean_stock_pct=float(s['exposure_sum']/s['days'])*100,mean_cash_pct=float(s['cash_sum']/s['days'])*100,equity_delta_usd=float(s['equity_delta']),zero_stock_days=s['zero_stock_days']) for k,s in stats.items()}
result=dict(status='READ_ONLY_REALIZED_EXPOSURE_ATTRIBUTION',results=out,source_hashes=pins,limitations=['ON/OFF assigns days to fixed QQQ market gate, even V27 which did not use this gate; descriptive only','Dollar equity changes partition realized account history, not causal avoided loss or missed profit','No ungated original selected-stock counterfactual exists here','Cash opportunity cost cannot be inferred by multiplying cash ratio by QQQ return'])
p=ROOT/'tmp/realized_exposure_attribution_20261106.json';p.write_text(json.dumps(result,indent=2));print(json.dumps(out,indent=2))

