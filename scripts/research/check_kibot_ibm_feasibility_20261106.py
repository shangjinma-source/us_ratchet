"""Offline public-sample feasibility only; no account changes or network."""
from pathlib import Path
from datetime import datetime
from decimal import Decimal as D
import csv,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'tmp/kibot_ibm_feasibility_20261106'
for source, expected in [
 (p/'daily_raw.response', '19d76b7c28898eb23d6f0dc46cc886bb5a738569de382f99a63480225927fa70'),
 (ROOT/'tmp/kibot_public_probe_20261106/ibm_raw.response', '68b0ca6adaef18241c478497ba9479e3dae72d8ed1b1bf7a4212ab0745ed5660'),
]:
 if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
  raise ValueError('FROZEN_PUBLIC_SAMPLE_HASH_MISMATCH: '+source.name)
rows=[]
for r in csv.reader((p/'daily_raw.response').read_text().splitlines()):
 if not r:continue
 day=datetime.strptime(r[0],'%m/%d/%Y').date().isoformat(); o,h,l,c=map(D,r[1:5]);assert l<=min(o,c)<=max(o,c)<=h
 rows.append(dict(day=day,open=o,high=h,low=l,close=c,volume=int(r[5])))
assert len({r['day'] for r in rows})==len(rows) and rows==sorted(rows,key=lambda r:r['day'])
mins={}
for r in csv.reader((ROOT/'tmp/kibot_public_probe_20261106/ibm_raw.response').read_text().splitlines()):
 if r:mins.setdefault(datetime.strptime(r[0],'%m/%d/%Y').date().isoformat(),[]).append(r)
comparisons=[]
for r in rows:
 if r['day'] not in mins:continue
 bars=mins[r['day']];agg=[D(bars[0][2]),max(D(x[3]) for x in bars),min(D(x[4]) for x in bars),D(bars[-1][5])]
 comparisons.append(dict(day=r['day'],minute_count=len(bars),daily=[str(r[k]) for k in ('open','high','low','close')],minute_aggregate=list(map(str,agg)),difference=list(map(str,[agg[j]-r[k] for j,k in enumerate(('open','high','low','close'))]))))
emas={}; prior=None;out=[];breaks=[];lastmonth=None
for i,r in enumerate(rows):
 if r['day']<'2026-07-01':continue
 month=r['day'][:7]
 if month!=lastmonth:
  warm=[x['close'] for x in rows[i-253:i]];assert len(warm)==253
  for n in (9,21,50):
   v=sum(warm[:n])/n
   for x in warm[n:]:v+=(x-v)*D(2)/D(n+1)
   emas[n]=v
  lastmonth=month
 old21=emas[21]
 for n in (9,21,50):emas[n]+=(r['close']-emas[n])*D(2)/D(n+1)
 trend=emas[9]>emas[21]>emas[50] and emas[21]>old21
 if prior and 1<=i-prior['i']<=5:
  prior['stop']=min(prior['stop'],r['low'])
  if trend and r['low']<=emas[9]<r['close'] and r['close']>emas[21] and r['high']-r['low']<prior['range'] and r['close']>rows[i-1]['high']:
   nxt=rows[i+1] if i+1<len(rows) else None
   out.append(dict(breakout=prior['day'],confirmation=r['day'],stop=str(prior['stop']),volume_contracts=r['volume']<prior['volume'],next_day=nxt['day'] if nxt else None,next_open=str(nxt['open']) if nxt else None,next_open_risk_percent=str((nxt['open']-prior['stop'])/nxt['open']*100) if nxt else None,minute_confirmation_covered=r['day'] in mins,minute_next_day_covered=bool(nxt and nxt['day'] in mins)))
   prior=None
 if trend and r['close']>max(x['high'] for x in rows[i-20:i]):
  prior=dict(i=i,day=r['day'],range=r['high']-r['low'],stop=D('Infinity'),volume=r['volume']);breaks.append(r['day'])
report=dict(status='FEASIBILITY_ONLY_NOT_BACKTEST',daily_rows=len(rows),daily_first=rows[0]['day'],daily_last=rows[-1]['day'],prior_daily_rows_before_minute_start=sum(r['day']<'2026-08-07' for r in rows),monthly_ema_seed='253 preceding daily closes; initial n SMA then EMA alpha 2/(n+1); month reset; raw nominal prices',breakout_dates=breaks,confirmations=out,overlap_days=len(comparisons),ohlc_exact_match_days=sum(all(D(x)==0 for x in z['difference']) for z in comparisons),scope='IBM outside original NDX domain; no split/action stream verified; raw provider feasibility only; no performance claim')
(p/'daily_minute_comparison.json').write_text(json.dumps(comparisons,indent=2));(p/'feasibility.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

b=mins['2026-11-05'];print('NOV5COUNT',len(b),'FIRST_LAST',b[0][1],b[-1][1])
c=D(b[-1][5]);h=max(D(x[3]) for x in b);l=min(D(x[4]) for x in b);old21=emas[21]
for n in (9,21,50):emas[n]+=(c-emas[n])*D(2)/D(n+1)
tests={'trend':emas[9]>emas[21]>emas[50] and emas[21]>old21,'touch_recover_ema9':l<=emas[9]<c,'above_ema21':c>emas[21],'smaller_range_than_breakout':bool(prior and h-l<prior['range']),'above_previous_high':c>rows[-1]['high'],'breakout_age':len(rows)-prior['i'] if prior else None}
report['nov5_observed_minute_aggregate_only']={'bars':len(b),'first':b[0][1],'last':b[-1][1],'checks':tests,'qualifies':all(tests[k] for k in tests if k!='breakout_age') and 1<=tests['breakout_age']<=5,'caveat':'Minute-derived final-day check only, missing bars unresolved; no invented daily provider record'}
(p/'feasibility.json').write_text(json.dumps(report,indent=2));print(tests)
