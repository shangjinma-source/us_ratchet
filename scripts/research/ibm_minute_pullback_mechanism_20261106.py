"""Frozen IBM minute execution mechanism only; not an account backtest."""
import csv,json,hashlib
from pathlib import Path
from datetime import datetime,timedelta
from decimal import Decimal as D
ROOT=Path(__file__).resolve().parents[2]
MINUTE=ROOT/'tmp/kibot_public_probe_20261106/ibm_raw.response'
DAILY=ROOT/'tmp/kibot_ibm_feasibility_20261106/daily_raw.response'
OUT=ROOT/'tmp/ibm_minute_pullback_20261106'
def clock(t):return int(t[:2])*60+int(t[3:])
def day(s):return datetime.strptime(s,'%m/%d/%Y').date().isoformat()
def load():
 daily=[];minutes={}
 for r in csv.reader(DAILY.read_text().splitlines()):
  if r:daily.append(dict(date=day(r[0]),o=D(r[1]),h=D(r[2]),l=D(r[3]),c=D(r[4]),v=int(r[5])))
 for r in csv.reader(MINUTE.read_text().splitlines()):
  if r:minutes.setdefault(day(r[0]),[]).append(dict(t=clock(r[1]),o=D(r[2]),h=D(r[3]),l=D(r[4]),c=D(r[5]),v=int(r[6])))
 validate(daily,minutes)
 return daily,minutes

def validate(daily,minutes):
 assert [x['date'] for x in daily]==sorted({x['date'] for x in daily})
 for bars in [daily,*minutes.values()]:
  for b in bars:assert b['l']<=min(b['o'],b['c'])<=max(b['o'],b['c'])<=b['h'] and b['l']>0 and b['v']>=0
 for bars in minutes.values():
  assert [b['t'] for b in bars]==sorted({b['t'] for b in bars})
  assert all(570<=b['t']<960 for b in bars)

def calendar(daily,minutes):
 lo,hi=min(minutes),max(minutes)
 return sorted({r['date'] for r in daily if lo<=r['date']<=hi}|set(minutes))

def filters(daily):
 result={};e={};month=None
 for i,r in enumerate(daily):
  if i<253:continue
  if r['date'][:7]!=month:
   warm=[x['c'] for x in daily[i-253:i]]
   for n in (9,21,50):
    z=sum(warm[:n])/n
    for c in warm[n:]:z+=(c-z)*D(2)/D(n+1)
    e[n]=z
   month=r['date'][:7]
  old=e[21]
  for n in (9,21,50):e[n]+=(r['c']-e[n])*D(2)/D(n+1)
  adv=sum(x['c']*x['v'] for x in daily[i-19:i+1])/20
  result[r['date']]=dict(trend=e[9]>e[21]>e[50] and e[21]>old,adv=adv,eligible=e[9]>e[21]>e[50] and e[21]>old and adv>=50000000)
 return result

def trigger(bars):
 if [b['t'] for b in bars[:5]]!=list(range(570,575)):return None,'INCOMPLETE_OPENING_OBSERVATION'
 high=max(b['h'] for b in bars[:5]);impulse=None;pull=None;stop=None
 for i in range(5,len(bars)):
  b=bars[i]
  if b['t']!=bars[i-1]['t']+1:return None,'GAP_BEFORE_TRIGGER'
  if impulse is None:
   if b['c']>high:impulse=i
   continue
  if pull is None:
   if b['c']<b['o']:pull=i;stop=b['l']
   continue
  if i-pull>5:return None,'FIRST_PULLBACK_EXPIRED'
  stop=min(stop,b['l'])
  if b['c']>bars[i-1]['h'] and b['c']>b['o']:
   return dict(index=i,entry_index=i+1,stop=stop,trigger_t=b['t'],entry_t=b['t']+1),None
 return None,'NO_FIRST_PULLBACK_TRIGGER'

def trade(minutes,dates,event,mode):
 di=dates.index(event['date']);end=di+4
 if end>=len(dates):return dict(status='INSUFFICIENT_FUTURE_OBSERVATION')
 start=di if mode=='MINUTE' else di+1;offset=event['entry_index'] if mode=='MINUTE' else 0;stop=event['stop']
 if mode=='NEXT_OPEN':
  tail=minutes[dates[di]][event['entry_index']:]
  if any(x['l']<=stop for x in tail):return dict(status='SETUP_INVALIDATED_BEFORE_NEXT_OPEN')
  if [x['t'] for x in tail]!=list(range(event['entry_t'],960)):return dict(status='UNKNOWN_SETUP_SURVIVAL_GAP')
  if dates[start] not in minutes:return dict(status='UNKNOWN_MISSING_EXECUTION_SESSION')
  if minutes[dates[start]][0]['t']!=570:return dict(status='MISSING_NEXT_OPEN')
 if dates[start] not in minutes:return dict(status='UNKNOWN_MISSING_EXECUTION_SESSION')
 if offset>=len(minutes[dates[start]]):return dict(status='UNKNOWN_MISSING_EXECUTION_MINUTE')
 b=minutes[dates[start]][offset]
 if mode=='MINUTE' and b['t']!=event['entry_t']:return dict(status='UNKNOWN_MISSING_EXECUTION_MINUTE')
 raw=b['o']
 if not D(0)<raw-stop<=raw*D('.03'):return dict(status='ENTRY_STOP_DISTANCE_REJECTED',raw_open=raw,stop=stop)
 price=raw*D('1.0005');risk=price-stop*D('.9995');q=min(int(D(100)/risk),int(D(2000)/price));target=price+3*risk
 if q<1:return dict(status='ZERO_AFFORDABLE_INTEGER_SHARES')
 base=dict(entry_date=dates[start],entry_time=b['t'],entry_price=price,quantity=q,stop=stop,target=target,planned_risk=q*risk)
 for j in range(start,end+1):
  if dates[j] not in minutes:return dict(base,status='UNKNOWN_MISSING_HOLDING_SESSION',date=dates[j])
  bars=minutes[dates[j]];begin=offset if j==start else 0;expected=bars[begin]['t'] if j==start else 570
  for x in bars[begin:]:
   if x['t']!=expected:return dict(base,status='UNKNOWN_MISSING_MINUTE',date=dates[j],expected=expected,observed=x['t'])
   expected+=1
   exitprice=None;reason=None
   if x['o']<=stop:exitprice=x['o']*D('.9995');reason='GAP_STOP'
   elif x['l']<=stop:exitprice=stop*D('.9995');reason='STOP_FIRST_IF_CONFLICT'
   elif x['h']>=target:exitprice=target*D('.9995');reason='THREE_R'
   if exitprice is not None:
    pnl=q*(exitprice-price);return dict(base,status='OBSERVED_PRICE_ONLY',exit_date=dates[j],exit_time=x['t'],exit_price=exitprice,reason=reason,pnl=pnl,r_multiple=pnl/(q*risk))
  if expected!=960:return dict(base,status='UNKNOWN_MISSING_SESSION_END',date=dates[j])
 exitprice=minutes[dates[end]][-1]['c']*D('.9995');pnl=q*(exitprice-price)
 return dict(base,status='OBSERVED_PRICE_ONLY',exit_date=dates[end],exit_time=959,exit_price=exitprice,reason='FIVE_SESSION_HORIZON',pnl=pnl,r_multiple=pnl/(q*risk))

def main():
 daily,minutes=load();f=filters(daily);dates=calendar(daily,minutes);daily_dates=[r['date'] for r in daily];events=[];screen=[]
 for d in dates:
  prev=max(x for x in daily_dates if x<d);eligible=f[prev]['eligible'];row=dict(date=d,prior_date=prev,**f[prev]);screen.append(row)
  if d not in minutes:row['trigger_status']='UNKNOWN_MISSING_SESSION';continue
  if not eligible:continue
  t,reason=trigger(minutes[d]);row['trigger_status']=reason or 'TRIGGERED'
  if not t:continue
  event=dict(date=d,**t);event['minute']=trade(minutes,dates,event,'MINUTE');event['next_open']=trade(minutes,dates,event,'NEXT_OPEN');events.append(event)
 paired=[e for e in events if e['minute']['status']==e['next_open']['status']=='OBSERVED_PRICE_ONLY']
 result=dict(evidence_status='MECHANISM_PROXY_NOT_DEPLOYABLE',sample_days=len(dates),eligible_days=sum(r['eligible'] for r in screen),events=events,screen=screen,paired_observed_count=len(paired),paired_price_pnl={k:sum(e[k]['pnl'] for e in paired) for k in ('minute','next_open')},source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (MINUTE,DAILY,Path(__file__),ROOT/'docs/candidates/ibm_minute_pullback_contract_20261106.md')},limitations=['IBM not historical NDX universe','No original PIT market-cap or AVWAP','Price-only fixed independent events; no account compounding','No dividends tax actual spread or HSBC monthly commissions','5-session/3R exit is experiment not original long trend exit','Missing minutes unknown, not flat bars','No annualization no bull-bear inference'])
 OUT.mkdir(exist_ok=True);(OUT/'result.json').write_text(json.dumps(result,default=str,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('screen','source_hashes')},default=str,indent=2))
if __name__=='__main__':main()

