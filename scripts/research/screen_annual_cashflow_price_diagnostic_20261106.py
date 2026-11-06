"""Fixed conditional cash-flow price diagnostic, not deployment evidence."""
import json,hashlib,math
from pathlib import Path
from fractions import Fraction as F
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
PANEL='tmp/annual_quality_local_diagnostic_20261106/descriptive_panel.json'
CONTRACT='docs/candidates/annual_cashflow_price_diagnostic_contract_20261106.md'
def quarterly(section):
 eligible=[];excluded=[]
 for row in section['rows']:
  reason=None
  if row['status']!='DESCRIPTIVE_RAW_SAME_VERSION':reason=row['status']
  else:
   fields=row['fields'];ni=F(fields['NetIncomeLoss']['value_exact']);ocf=F(fields['NetCashProvidedByUsedInOperatingActivities']['value_exact']);assets=F(fields['Assets']['value_exact'])
   assert assets>0 and all(all(d<section['cutoff'] for d in fields[k]['filed_dates']) for k in ('NetIncomeLoss','NetCashProvidedByUsedInOperatingActivities','Assets'))
   if ni<=0 or ocf<=0:reason='NI_OR_OCF_NOT_POSITIVE'
  if reason:excluded.append(dict(security_id=row['security_id'],ticker=row['ticker'],reason=reason));continue
  eligible.append(dict(security_id=row['security_id'],issuer_id=row['issuer_id'],ticker=row['ticker'],score_exact=str(ocf/assets),accession=row['accession'],period_end=row['period_end'],availability_layer=row['availability_layer'],acceptance=row['acceptance'],fields=fields,source_hashes=row['source_hashes']))
 eligible.sort(key=lambda x:(-F(x['score_exact']),x['security_id']));selected=[];issuers=set()
 for row in eligible:
  if row['issuer_id'] in issuers:continue
  selected.append(row);issuers.add(row['issuer_id'])
  if len(selected)==10:break
 return dict(cutoff=section['cutoff'],domain=section['domain'],descriptive_available=section['descriptive_available'],positive_eligible=len(eligible),selected=selected,excluded=excluded)

def affordable_targets(equity,names,prior):
 def cost(base):return sum(abs((base/10 if s in names else 0)-prior.get(s,0)) for s in set(names)|set(prior))*.0005
 lo,hi=0.,equity
 for _ in range(60):
  mid=(lo+hi)/2
  if len(names)*mid/10+cost(mid)<=equity:lo=mid
  else:hi=mid
 allocations={s:lo/10 for s in names};fee=cost(lo);return allocations,equity-sum(allocations.values())-fee,fee

def main():
 pins={}
 def read(path,exact=False):
  raw=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(raw).hexdigest();return loads(raw.decode()) if exact else json.loads(raw)
 panel=read(PANEL);read(CONTRACT) if False else None
 for source,digest in panel['source_hashes'].items():
  if hashlib.sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('PANEL_SOURCE_CHANGED:'+source)
 quarters=[quarterly(s) for s in panel['results']];rosters=read('tmp/cross_sectional_momentum_static_20261105/result.json')['rows'];results=[]
 for window,path in [('2021_2023','tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),('2024_2026','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')]:
  training={}
  for outer in read(path)['windows']:
   w=outer.get('window',outer);training[w.get('decision_cutoff',w.get('decision_date'))]=w
  execution=read('tmp/relative_strength_downside_20261106_'+window+'/execution_inputs.json',True)['document'];rows=[r for r in rosters if r['window']==window];equity=20000.;prior={};cash=equity;ledger=[];months=[];missing=[];proxies=[];fee_total=0;pending=set()
  for i,row in enumerate(rows[:-1]):
   day=row['decision_date'];nxt=rows[i+1]['decision_date'];quarter=max((q for q in quarters if q['cutoff']<=day),key=lambda q:q['cutoff']);legal={r['security_id'] for r in row['ranked']};selected=[s for s in quarter['selected'] if s['security_id'] in legal];removed=[s['security_id'] for s in quarter['selected'] if s['security_id'] not in legal];names=[s['security_id'] for s in selected] if row['gate']['risk_on'] else []
   tw=training[nxt];dates=tw['training_dates'];assert dates==sorted(set(dates)) and dates[-1]==nxt;index=dates.index(day);candidates={c['security_id']:c for c in tw['candidates'] if c.get('security_id')}
   for sid in names:
    if sid not in candidates:
     values=[]
     for d in dates:
      if sid=='research:security:alxn' and d>='2021-07-21':v=F(60)+F('2.1243')*F(execution['ohlc']['research:security:azn'][d]['close']);kind='ALXN_CONTINUOUS_FRACTIONAL_SUCCESSOR_VALUE'
      elif sid=='security:0001353283:848637104' and d>='2024-03-18':v=F(157);kind='SPLK_CASH157_VALUATION'
      else:v=execution['ohlc'].get(sid,{}).get(d,{}).get('close');kind=None
      values.append(v)
      if kind and d>=day:proxies.append(dict(security_id=sid,date=d,kind=kind))
     if all(v is not None for v in values[index:]):candidates[sid]={'training_close':values}
   bad=[s for s in names if s not in candidates or len(candidates[s]['training_close'])!=253 or any(v is None or F(v)<=0 for v in candidates[s]['training_close'][index:])]
   month=dict(decision_date=day,quarter_cutoff=quarter['cutoff'],risk_on=row['gate']['risk_on'],quarter_selected=[s['security_id'] for s in quarter['selected']],removed_not_legal=removed,configured=names,missing_price=bad);months.append(month)
   if bad:missing.append(dict(day=day,securities=bad));break
   allocations,cash,fee=affordable_targets(equity,names,prior);assert cash>=-1e-8;fee_total+=fee;month.update(target_values=allocations.copy(),cash_after_cost=cash,reallocation_slippage=fee)
   peaks={s:1. for s in names};cumulative={s:1. for s in names};pending&=set(names)
   for j in range(index+1,len(dates)):
    for sid in list(allocations):
     prices=candidates[sid]['training_close'];ratio=float(F(prices[j])/F(prices[j-1]));allocations[sid]*=ratio;cumulative[sid]*=ratio;peaks[sid]=max(peaks[sid],cumulative[sid])
     if sid in pending:fee=allocations[sid]*.0005;fee_total+=fee;cash+=allocations.pop(sid)-fee;pending.remove(sid)
     elif cumulative[sid]<=peaks[sid]*.8:pending.add(sid)
    equity=cash+sum(allocations.values());ledger.append(dict(date=dates[j],equity=equity,cash=cash,stock_values=allocations.copy(),quarter_cutoff=quarter['cutoff']))
   prior=allocations
  result=dict(window=window,status='MISSING_PRICE_NO_FULL_RESULT' if missing else 'CONDITIONAL_PRICE_DIAGNOSTIC_ONLY',months=months,ledger=ledger,missing=missing,explicit_valuation_proxies=proxies,slippage_cost_proxy=fee_total,terminal_month_excluded=rows[-1]['decision_date'],metrics=None)
  if not missing:
   from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
   result['metrics']=metrics(ledger,rows[0]['decision_date'],0);result['metrics']['fills']=None
  results.append(result)
 for source in (CONTRACT,str(Path(__file__).relative_to(ROOT)),'scripts/research/summarize_cross_month_held_peak_20261105.py'):pins[source]=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
 out=dict(evidence_status='DIAGNOSTIC_NOT_DEPLOYABLE',quarterly_selections=quarters,results=results,source_hashes=pins,financial_sources=panel['source_hashes'],limitations=['Same-close optimistic execution','Fractional stock values, no actual holdings or corporate-action account','Missing complete dividends taxes HSBC commission','Price-only historical conditional coordinate','Last month omitted because next training snapshot unavailable','No PIT or QMJ or independent OOS certification','Fee-affordable target values avoid negative cash; all targets retain 10pct ceiling','Quarter roster intersect current legal domain, no replacements; membership recovery can restore same original name','Next-close pending stops carried across month if same name retained; peaks reset monthly'])
 target=ROOT/'tmp/annual_cashflow_price_diagnostic_20261106.json';target.write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps([dict(window=r['window'],status=r['status'],metrics=r['metrics'],missing=r['missing']) for r in results],indent=2))
if __name__=='__main__':main()
