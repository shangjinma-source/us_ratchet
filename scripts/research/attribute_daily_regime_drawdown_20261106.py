"""Read-only exact daily price-path attribution of observed worst drawdown."""
import json,hashlib
from pathlib import Path
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[2]
def main():
 pins={}
 def read(path):
  raw=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
 doc=read('tmp/profitability_daily_regime_20261106_PROFITABLE.json');r=doc['results'][1];rows=r['ledger'];peak=r['metrics']['peak'];trough=r['metrics']['trough'];training={}
 for outer in read('tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')['windows']:
  w=outer.get('window',outer);training[w.get('decision_cutoff',w.get('decision_date'))]=w
 rosters=read('tmp/cross_sectional_momentum_static_20261105/result.json')['rows'];ticks={x['security_id']:x['ticker'] for rr in rosters for x in rr['ranked']};months={m['decision_date']:m for m in r['months']};totals={};daily=[]
 for previous,current in zip(rows,rows[1:]):
  if not peak<current['date']<=trough:continue
  holdings=months[previous['date']]['target_values'] if previous['date'] in months else previous['stock_values']
  endpoint=min(d for d in training if d>=current['date']);w=training[endpoint];dates=w['training_dates'];j=dates.index(current['date']);assert dates[j-1]==previous['date'];cs={c['security_id']:c for c in w['candidates'] if c.get('security_id')};parts={}
  for sid,value in holdings.items():
   prices=cs[sid]['training_close'];pnl=value*(float(F(prices[j])/F(prices[j-1]))-1);parts[sid]=pnl;totals[sid]=totals.get(sid,0)+pnl
  delta=current['equity']-previous['equity'];daily.append(dict(date=current['date'],risk_on_after_close=current['risk_on'],pnl_by_sid=parts,equity_change=delta,cost_residual=sum(parts.values())-delta))
 a=next(x for x in rows if x['date']==peak);b=next(x for x in rows if x['date']==trough);out=dict(status='READ_ONLY_OBSERVED_PATH_NOT_COUNTERFACTUAL',peak_date=peak,trough_date=trough,peak_equity=a['equity'],trough_equity=b['equity'],equity_change=b['equity']-a['equity'],stock_price_pnl=sum(totals.values()),cost_residual=sum(x['cost_residual'] for x in daily),stock_contributions=sorted([dict(sid=s,ticker=ticks.get(s),pnl=v) for s,v in totals.items()],key=lambda x:x['pnl']),transitions=[t for t in r['transitions'] if peak<t['execution_date']<=trough],daily=daily,source_hashes=pins)
 assert abs(out['stock_price_pnl']-out['cost_residual']-out['equity_change'])<1e-7
 (ROOT/'tmp/daily_regime_drawdown_attribution_20261106.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ('daily','source_hashes')},indent=2))
if __name__=='__main__':main()
