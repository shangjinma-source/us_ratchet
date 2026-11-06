"""Fixed same-engine profitability eligibility increment; only two arms."""
import json,hashlib
from pathlib import Path
from fractions import Fraction as F
from backtest.research_exact_fraction_json import loads
from docs.candidates.profitability_smci_price_bridge_20261106 import load_bridge,old_share_series,OLD
def affordable_targets(equity,names,prior,pending=()):
 def targets(base):return {s:min(base/10,prior.get(s,0.)) if s in pending else base/10 for s in names}
 def fee(target):return .0005*sum(abs(target.get(s,0.)-prior.get(s,0.)) for s in set(target)|set(prior))
 lo,hi=0.,equity
 for _ in range(60):
  mid=(lo+hi)/2;target=targets(mid)
  if sum(target.values())+fee(target)<=equity:lo=mid
  else:hi=mid
 target=targets(lo);cost=fee(target);return target,equity-sum(target.values())-cost,cost
ROOT=Path(__file__).resolve().parents[2]
PANEL='tmp/annual_quality_local_diagnostic_20261106/descriptive_panel.json'
CONTRACT='docs/candidates/profitability_open_regime_contract_20261106.md'
def build_decision(roster,panel,arm):
 assert arm in ('CONTROL','PROFITABLE')
 section=max((s for s in panel['results'] if s['cutoff']<=roster['decision_date']),key=lambda s:s['cutoff']);financial={r['security_id']:r for r in section['rows']};selected=[];issuers=set();audit=[]
 for candidate in roster['ranked']:
  sid=candidate['security_id'];f=financial.get(sid);reason='ELIGIBLE';available=False
  if f is None:reason='NOT_IN_AVAILABLE_QUARTER_DOMAIN'
  elif f['status']!='DESCRIPTIVE_RAW_SAME_VERSION':reason=f['status']
  else:
   fields=f['fields'];ni=F(fields['NetIncomeLoss']['value_exact']);ocf=F(fields['NetCashProvidedByUsedInOperatingActivities']['value_exact']);assets=F(fields['Assets']['value_exact']);assert assets>0
   assert all(all(d<section['cutoff'] for d in fields[k]['filed_dates']) for k in ('NetIncomeLoss','NetCashProvidedByUsedInOperatingActivities','Assets'))
   available=True
   if ni<=0 or ocf<=0:reason='NI_OR_OCF_NOT_POSITIVE'
  accepted=arm=='CONTROL' or reason=='ELIGIBLE';decision='NOT_SELECTED_FINANCIAL_QUALIFICATION'
  if accepted:
   if candidate['issuer_id'] in issuers:decision='ISSUER_ALREADY_SELECTED'
   elif len(selected)>=10:decision='BELOW_TOP_TEN'
   else:
    item=dict(candidate)
    item['financial_version']=None if not available else {k:f.get(k) for k in ('accession','period_end','acceptance','availability_layer','fields','source_hashes')}
    selected.append(item);issuers.add(candidate['issuer_id']);decision='SELECTED'
  audit.append(dict(security_id=sid,ticker=candidate['ticker'],rank=candidate['rank'],financial_reason=reason,selection_decision=decision))
 if arm=='CONTROL':assert [r['security_id'] for r in selected]==[r['security_id'] for r in roster['selected']]
 return dict(cutoff=roster['decision_date'],financial_cutoff=section['cutoff'],domain=len(roster['ranked']),selected=selected,candidate_audit=audit)


def read_qqq(pins):
 import gzip,datetime
 prices={}
 for path in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
  raw=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(raw).hexdigest();payload=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw);chart=payload['chart']['result'][0]
  for t,c in zip(chart['timestamp'],chart['indicators']['quote'][0]['close']):
   if c is None:raise ValueError('QQQ_NULL_PRICE')
   d=datetime.datetime.fromtimestamp(t,datetime.timezone.utc).date().isoformat()
   if d in prices and abs(prices[d]-c)>1e-7:raise ValueError('QQQ_OVERLAP_COORDINATE_MISMATCH:'+d)
   prices[d]=c
 return prices

def market_states(prices,mode):
 dates=sorted(prices);states={};state=False;previous=None;ema=None
 if mode not in ('SMA200','EMA20'):raise ValueError('INVALID_MODE')
 for i,d in enumerate(dates):
  if mode=='SMA200':
   if i<199:continue
   average=sum(prices[x] for x in dates[i-199:i+1])/200
  else:
   if i<19:continue
   ema=sum(prices[x] for x in dates[:20])/20 if ema is None else ema+(prices[d]-ema)*2/21
   average=ema
  above=prices[d]>average
  if previous is not None:
   if above==previous:state=above
   states[d]=state
  previous=above
 return states

def run(mode):
 arm='PROFITABLE'
 pins={}
 def read(path,exact=False):
  raw=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(raw).hexdigest();return loads(raw.decode()) if exact else json.loads(raw)
 panel=read(PANEL);smci_ohlc=load_bridge(pins);qqq=read_qqq(pins);market=market_states(qqq,mode)
 for source,digest in panel['source_hashes'].items():
  if hashlib.sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('PANEL_SOURCE_CHANGED:'+source)
 rosters=read('tmp/cross_sectional_momentum_static_20261105/result.json')['rows'];quarters=[build_decision(r,panel,arm) for r in rosters];results=[]
 for window,path in [('2021_2023','tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),('2024_2026','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')]:
  training={}
  for outer in read(path)['windows']:
   w=outer.get('window',outer);td=w['training_dates'];assert len(td)==253 and td==sorted(set(td));assert [d for d in sorted(qqq) if td[0]<=d<=td[-1]]==td, 'QQQ_WARMUP_CALENDAR_MISMATCH';training[w.get('decision_cutoff',w.get('decision_date'))]=w
  execution=read('tmp/relative_strength_downside_20261106_'+window+'/execution_inputs.json',True)['document'];rows=[r for r in rosters if r['window']==window];equity=20000.;prior={};cash=equity;ledger=[];months=[];missing=[];proxies=[];fee_total=0;pending=set();risk_on=False;transitions=[]
  for i,row in enumerate(rows[:-1]):
   day=row['decision_date'];nxt=rows[i+1]['decision_date'];quarter=max((q for q in quarters if q['cutoff']<=day),key=lambda q:q['cutoff']);legal={r['security_id'] for r in row['ranked']};selected=[s for s in quarter['selected'] if s['security_id'] in legal];removed=[s['security_id'] for s in quarter['selected'] if s['security_id'] not in legal];names=[s['security_id'] for s in selected]
   tw=training[nxt];dates=tw['training_dates'];assert dates==sorted(set(dates)) and dates[-1]==nxt;index=dates.index(day);assert [d for d in sorted(qqq) if day<=d<=nxt]==dates[index:], 'QQQ_SESSION_MISMATCH';candidates={c['security_id']:c for c in tw['candidates'] if c.get('security_id')}
   for sid in names:
    if sid not in candidates and sid==OLD and day=='2024-09-30':
     candidates[sid]={'training_close':old_share_series(sid,dates,index,smci_ohlc)}
     proxies.append(dict(security_id=sid,date=day,kind='EXACT_SMCI_OLD_SHARE_PRICE_COORDINATE_1_TO_10'))
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
   month=dict(market_state_at_anchor=risk_on,decision_date=day,financial_cutoff=quarter['financial_cutoff'],pending_before=sorted(pending),old_stock_values=prior.copy(),quarter_cutoff=quarter['cutoff'],baseline_monthly_risk_on=row['gate']['risk_on'],quarter_selected=[s['security_id'] for s in quarter['selected']],removed_not_legal=removed,configured=names,missing_price=bad);months.append(month)
   if bad:missing.append(dict(day=day,securities=bad));break
   allocations,cash,fee=affordable_targets(equity,names if risk_on else [],prior,pending);assert cash>=-1e-8;fee_total+=fee;month.update(target_values=allocations.copy(),cash_after_cost=cash,reallocation_slippage=fee)
   peaks={s:1. for s in allocations};cumulative={s:1. for s in allocations};pending&=set(allocations);stopped=set()
   for j in range(index+1,len(dates)):
    d=dates[j];previous=dates[j-1]
    if d not in qqq or previous not in market:raise ValueError('QQQ_WARMUP_OR_SESSION_MISSING:'+previous)
    desired=market[previous];changing=desired!=risk_on;ratios={sid:float(F(candidates[sid]['training_close'][j])/F(candidates[sid]['training_close'][j-1])) for sid in set(allocations)|set(names)}
    needed=(set(allocations)| (set(names)-stopped if desired else set())) if changing else set()
    open_close={}
    for sid in needed:
     bar=execution['ohlc'].get(sid,{}).get(d)
     if bar is None and sid==OLD and d>='2024-10-01':bar=smci_ohlc.get('security:0001375365:86800U302',{}).get(d)
     if not bar or not bar.get('open') or not bar.get('close') or F(bar['open'])<=0 or F(bar['close'])<=0:
      missing.append(dict(day=d,securities=[sid],reason='ACTUAL_REGIME_OPEN_OHLC_MISSING'));break
     open_close[sid]=float(F(bar['open'])/F(bar['close']))
    if missing:break
    if changing:
     for sid in allocations:allocations[sid]*=ratios[sid]*open_close[sid];cumulative[sid]*=ratios[sid]*open_close[sid]
     equity=cash+sum(allocations.values());target_names=[sid for sid in names if sid not in stopped] if desired else []
     old=allocations.copy();allocations,cash,fee=affordable_targets(equity,target_names,old,pending);assert cash>=-1e-8;fee_total+=fee
     transitions.append(dict(signal_date=previous,execution_date=d,execution_phase='OPEN',from_on=risk_on,to_on=desired,cost=fee,stopped_excluded=sorted(stopped)))
     for sid in allocations:
      if sid not in old:cumulative[sid]=1.;peaks[sid]=1.
     pending&=set(allocations);risk_on=desired
    for sid in list(allocations):
     ratio=1/open_close[sid] if changing else ratios[sid];allocations[sid]*=ratio;cumulative[sid]*=ratio;peaks[sid]=max(peaks[sid],cumulative[sid])
     if sid in pending:fee=allocations[sid]*.0005;fee_total+=fee;cash+=allocations.pop(sid)-fee;pending.remove(sid);stopped.add(sid)
     elif cumulative[sid]<=peaks[sid]*.8:pending.add(sid)
    equity=cash+sum(allocations.values());ledger.append(dict(date=d,equity=equity,cash=cash,stock_values=allocations.copy(),quarter_cutoff=quarter['cutoff'],risk_on=risk_on,signal_date=previous))
   if missing:break
   prior=allocations
  result=dict(warmup=dict(anchor=rows[0]['decision_date'],qqq_history_start=min(qqq),available_bars=sum(d<=rows[0]['decision_date'] for d in qqq),confirmed_anchor_state=market.get(rows[0]['decision_date']),initial_execution=ledger[0]['date'] if ledger else None),transitions=transitions,window=window,status='MISSING_PRICE_NO_FULL_RESULT' if missing else 'CONDITIONAL_PRICE_DIAGNOSTIC_ONLY',months=months,ledger=ledger,missing=missing,explicit_valuation_proxies=proxies,slippage_cost_proxy=fee_total,terminal_month_excluded=rows[-1]['decision_date'],metrics=None)
  if not missing:
   from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
   result['metrics']=metrics(ledger,rows[0]['decision_date'],0);result['metrics']['fills']=None
   anchor=rows[0]['decision_date'];units=20000/(qqq[anchor]*1.0005);bench=[dict(date=r['date'],equity=units*qqq[r['date']]) for r in ledger];result['qqq_price_5bp_reference']=dict(metrics=metrics(bench,anchor,0),initial_fee=units*qqq[anchor]*.0005,anchor=anchor,anchor_price=qqq[anchor],limitations='Price only, fractional buy at anchor close with 5bp entry, no dividend/tax; no exit fee because holdings not liquidated')
   result['groups']={k:dict(days=sum(r['risk_on']==v for r in ledger),mean_stock_pct=100*sum(sum(r['stock_values'].values())/r['equity'] for r in ledger if r['risk_on']==v)/max(1,sum(r['risk_on']==v for r in ledger))) for k,v in [('ON',True),('OFF',False)]}
  results.append(result)
 for source in ('docs/candidates/profitability_smci_price_bridge_20261106.py',CONTRACT,'docs/candidates/profitability_momentum_control_contract_20261106.md',str(Path(__file__).relative_to(ROOT)),'scripts/research/summarize_cross_month_held_peak_20261105.py'):pins[source]=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
 out=dict(market_mode=mode,evidence_status='DIAGNOSTIC_NOT_DEPLOYABLE',arm=arm,monthly_selection_audit=quarters,results=results,source_hashes=pins,financial_sources=panel['source_hashes'],limitations=['Same-close optimistic execution','Fractional stock values, no actual holdings or corporate-action account','Missing complete dividends taxes HSBC commission','Price-only historical conditional coordinate','Last month omitted because next training snapshot unavailable','No PIT or QMJ or independent OOS certification','Fee-affordable target values avoid negative cash; all targets retain 10pct ceiling','Daily fixed market two-close confirmation executed next OPEN with actual open/close decomposition; fixed monthly roster re-entry; current-month stopped names not bought again','Monthly same 252/21 ranking; PROFITABLE adds available quarterly NI and OCF positive qualification; missingness effect not separated','Pending targets capped at prior stock value, no top-up; next-close stop preserved; peaks reset monthly'])
 target=ROOT/('tmp/profitability_open_regime_20261106_'+mode+'.json');target.write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps([dict(arm=arm,window=r['window'],status=r['status'],metrics=r['metrics'],missing=r['missing']) for r in results],indent=2))
if __name__=='__main__':
 for mode in ('SMA200','EMA20'):run(mode)
