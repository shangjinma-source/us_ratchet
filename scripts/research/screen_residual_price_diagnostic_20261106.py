"""Non-decision price screening: fractional close-to-close, not account backtest. ALXN continuous fractional successor basket and SPLK cash157 are valuation proxies, not broker settlement."""
import json,math,hashlib
from pathlib import Path
from fractions import Fraction as F
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
rosters=json.loads((ROOT/'tmp/residual_momentum_feasibility_20261106.json').read_bytes())['rows']
for row in rosters:
 row['decision_date']=row['date'];row['gate']={'risk_on':row['risk_on']}
results=[]
for window,path in [('2021_2023','tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),('2024_2026','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')]:
 training={}
 for outer in json.loads((ROOT/path).read_bytes())['windows']:
  w=outer.get('window',outer);training[w.get('decision_cutoff',w.get('decision_date'))]=w
 execution=loads((ROOT/('tmp/relative_strength_downside_20261106_'+window)/'execution_inputs.json').read_text())['document']
 rows=[r for r in rosters if r['window']==window];equity=20000.;ledger=[];turnover=0.;missing=[];prior={};cash=equity
 for i,row in enumerate(rows[:-1]):
  day=row['decision_date'];nextday=rows[i+1]['decision_date'];tw=training[nextday];dates=tw['training_dates'];index=dates.index(day);candidates={c['security_id']:c for c in tw['candidates'] if c.get('security_id')}
  selected=row['selected'] if row['gate']['risk_on'] else []
  names=[s['security_id'] for s in selected]
  for sid in names:
   if sid in candidates:continue
   values=[]
   for d in dates:
    if sid=='research:security:alxn' and d>='2021-07-21':value=F(60)+F('2.1243')*F(execution['ohlc']['research:security:azn'][d]['close'])
    elif sid=='security:0001353283:848637104' and d>='2024-03-18':value=F(157)
    else:value=execution['ohlc'].get(sid,{}).get(d,{}).get('close')
    values.append(value)
   if all(v is not None for v in values[index:]):candidates[sid]={'training_close':values}
  if any(s not in candidates for s in names):
   missing.append({'day':day,'missing':[s for s in names if s not in candidates]});break
  allocations={s:equity/10 for s in names};turn=sum(abs(allocations.get(s,0)-prior.get(s,0)) for s in set(allocations)|set(prior));cash=equity-sum(allocations.values())-turn*.0005;turnover+=turn
  peaks={s:1. for s in names};cumulative={s:1. for s in names};pending=set()
  for j in range(index+1,len(dates)):
   for s in list(allocations):
    prices=candidates[s]['training_close'];ratio=float(F(prices[j])/F(prices[j-1]));allocations[s]*=ratio;cumulative[s]*=ratio;peaks[s]=max(peaks[s],cumulative[s])
    if s in pending:
     cash+=allocations.pop(s)*.9995;pending.remove(s)
    elif cumulative[s]<=peaks[s]*.8:pending.add(s)
   equity=cash+sum(allocations.values());ledger.append({'date':dates[j],'equity':equity})
  prior=allocations
 if missing:results.append({'window':window,'status':'MISSING_PRICE_NO_RESULT','missing':missing});continue
 from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
 report=metrics(ledger,rows[0]['decision_date'],0)
 report['fills']=None # Diagnostic does not count executed orders.
 results.append({'window':window,'status':'PRICE_PROXY_ONLY_NOT_ACCOUNT_BACKTEST','metrics':report,'ledger':ledger,'end':ledger[-1]['date'],'terminal_month_excluded':rows[-1]['decision_date'],'method':'Fractional monthly close targets; training price ratios; close stop exits next close; monthly stop reference reset; no dividend receivables or real corporate-action accounting; 5bp turnover charge.'})
out=ROOT/'tmp/residual_price_diagnostic_20261106.json';out.write_text(json.dumps(results,indent=2),encoding='utf-8')
for r in results:print({k:v for k,v in r.items() if k!='ledger'},flush=True)

paths=['tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json','tmp/relative_strength_downside_20261106_2021_2023/execution_inputs.json','tmp/relative_strength_downside_20261106_2024_2026/execution_inputs.json','scripts/research/summarize_cross_month_held_peak_20261105.py','tmp/residual_momentum_feasibility_20261106.json','docs/candidates/residual_price_diagnostic_contract_20261106.md',str(Path(__file__).relative_to(ROOT))]
(ROOT/'tmp/residual_price_diagnostic_sources_20261106.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},indent=2))
