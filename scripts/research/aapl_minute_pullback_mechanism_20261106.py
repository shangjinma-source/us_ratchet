"""Same frozen rule on the separate FirstRate AAPL public sample."""
from scripts.research import ibm_minute_pullback_mechanism_20261106 as m
from pathlib import Path
import csv,zipfile,json,hashlib
from datetime import datetime
D=m.D
ROOT=m.ROOT
p=ROOT/'tmp/ibm_minute_pullback_20261106'
def main():
 source=ROOT/'tmp/free_minute_sources_20261106/AAPL.zip';z=zipfile.ZipFile(source);daily=[];minutes={}
 for r in csv.reader((p/'aapl_daily.response').read_text().splitlines()):
  if r:daily.append(dict(date=m.day(r[0]),o=D(r[1]),h=D(r[2]),l=D(r[3]),c=D(r[4]),v=int(r[5])))
 for r in csv.reader(z.read('AAPL_1min.csv').decode().splitlines()):
  t=m.clock(r[0][11:16])
  if 570<=t<960:minutes.setdefault(r[0][:10],[]).append(dict(t=t,o=D(r[1]),h=D(r[2]),l=D(r[3]),c=D(r[4]),v=int(r[5])))
 m.validate(daily,minutes);f=m.filters(daily);dates=m.calendar(daily,minutes);daily_dates=[r['date'] for r in daily];events=[];screen=[]
 for d in dates:
  prev=max(x for x in daily_dates if x<d);row=dict(date=d,prior_date=prev,**f[prev]);screen.append(row)
  if d not in minutes:row['trigger_status']='UNKNOWN_MISSING_SESSION';continue
  if not row['eligible']:continue
  t,reason=m.trigger(minutes[d]);row['trigger_status']=reason or 'TRIGGERED'
  if t:
   event=dict(date=d,**t);event['minute']=m.trade(minutes,dates,event,'MINUTE');event['next_open']=m.trade(minutes,dates,event,'NEXT_OPEN');events.append(event)
 paired=[e for e in events if e['minute']['status']==e['next_open']['status']=='OBSERVED_PRICE_ONLY']
 result=dict(evidence_status='MECHANISM_PROXY_NOT_DEPLOYABLE',ticker='AAPL',days=len(dates),eligible_days=sum(r['eligible'] for r in screen),events=events,screen=screen,paired_count=len(paired),paired_price_pnl={k:sum(e[k]['pnl'] for e in paired) for k in ('minute','next_open')},sources={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in (source,p/'aapl_daily.response',Path(__file__),Path(m.__file__),ROOT/'docs/candidates/ibm_minute_pullback_contract_20261106.md')},limitations=['Same limitations as IBM frozen contract','Cross-vendor warmup OHLC matched 10 overlapping dates; not complete corporate action certification','No account return or annualization'])
 (p/'aapl_result.json').write_text(json.dumps(result,default=str,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('screen','sources')},default=str,indent=2))
if __name__=='__main__':main()
