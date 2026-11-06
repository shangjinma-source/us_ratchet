"""Descriptive ON/OFF decomposition of frozen v2 paths, not new trading."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
results=[];pins={}
for arm in ('CONTROL','PROFITABLE'):
 path=ROOT/('tmp/profitability_momentum_control_v2_20261106_'+arm+'.json');raw=path.read_bytes();pins[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();document=json.loads(raw)
 for window in document['results']:
  groups={};prior=20000.;months=window['months'];transitions=sum(a['risk_on']!=b['risk_on'] for a,b in zip(months,months[1:]));dates=[]
  for a,b in zip(months,months[1:]):
   if a['risk_on']!=b['risk_on']:dates.append(dict(decision_date=b['decision_date'],from_on=a['risk_on'],to_on=b['risk_on']))
  for row in window['ledger']:
   month=max((m for m in months if m['decision_date']<row['date']),key=lambda m:m['decision_date']);key='ON' if month['risk_on'] else 'OFF';g=groups.setdefault(key,dict(days=0,equity_change_usd=0.,stock_exposure_sum=0.,cash_exposure_sum=0.,zero_stock_days=0));g['days']+=1;g['equity_change_usd']+=row['equity']-prior;g['stock_exposure_sum']+=sum(row['stock_values'].values())/row['equity'];g['cash_exposure_sum']+=row['cash']/row['equity'];g['zero_stock_days']+=not row['stock_values'];prior=row['equity']
  for g in groups.values():g['mean_stock_pct']=100*g.pop('stock_exposure_sum')/g['days'];g['mean_cash_pct']=100*g.pop('cash_exposure_sum')/g['days']
  results.append(dict(arm=arm,window=window['window'],groups=groups,transitions=transitions,transition_dates=dates,year2022=window['metrics']['annual'].get('2022'),limitations='Realized daily equity difference partition, not causal avoided loss. Daily record includes previous close rebalance cost; cash-only switch day can have fee loss. Monthly gate not perfect bull/bear foresight.'))
out=dict(status='READ_ONLY_FROZEN_V2_PATH_ATTRIBUTION',results=results,source_hashes=pins);(ROOT/'tmp/profitability_momentum_v2_regimes_20261106.json').write_text(json.dumps(out,indent=2));print(json.dumps(results,indent=2))
