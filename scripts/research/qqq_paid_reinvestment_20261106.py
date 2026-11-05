"""Fixed integer QQQ reinvestment; issuer payable cash at close, next session open."""
import json,gzip
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from hashlib import sha256
from scripts.research.rsi2_complete_window_metrics_20261106 import WINDOWS,summarize,read,ROOT

def run_book(days,panel,events,initial=20000):
 cash=F(initial);shares=0;claims=[];ledger=[];orders=[]
 for day in days[1:]:
  for event in events:
   if event['ex_date']==day and shares:claims.append(dict(**event,value=shares*F(event['amount']),paid=False))
  price=F(panel[day]['open'])*F(2001,2000);quantity=int(cash//price)
  if quantity:
   cash-=quantity*price;shares+=quantity;orders.append(dict(date=day,side='BUY',quantity=quantity,price=str(price),cash_after=str(cash),reason='INITIAL_OR_AVAILABLE_CASH_REINVESTMENT'))
  for claim in claims:
   if not claim['paid'] and claim['payment_date']<=day:cash+=claim['value'];claim['paid']=True;claim['posted_date']=day
  receivable=sum((c['value'] for c in claims if not c['paid']),F(0));equity=cash+shares*F(panel[day]['close'])+receivable
  ledger.append(dict(date=day,cash=str(cash),shares=shares,dividend_receivable=str(receivable),equity=str(equity)))
 return dict(status='COMPLETE',reason=None,initial_cash=str(initial),daily_ledger=ledger,order_log=orders,claims=[{**c,'value':str(c['value'])} for c in claims],external_flows='0')

def run():
 out=ROOT/'tmp/qqq_reinvest_20261106';pins=read(ROOT/'tmp/qqq_fair_hold_20261105/summary.json')['source_hashes'];panel={};provider_events={}
 for name in ['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']:
  raw=(ROOT/name).read_bytes();assert sha256(raw).hexdigest()==pins[name];body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0];assert body['meta']['symbol']=='QQQ' and not body.get('events',{}).get('splits');q=body['indicators']['quote'][0]
  for i,t in enumerate(body['timestamp']):
   if q['open'][i] is None or q['close'][i] is None:continue
   day=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat();v={k:str(F(q[k][i])) for k in ['open','close']}
   if day in panel:assert panel[day]==v
   panel[day]=v
  for e in body.get('events',{}).get('dividends',{}).values():provider_events[datetime.fromtimestamp(e['date'],ZoneInfo('America/New_York')).date().isoformat()]=F(e['amount'])
 raw=(out/'nasdaq_dividends.json').read_bytes();pins['tmp/qqq_reinvest_20261106/nasdaq_dividends.json']=sha256(raw).hexdigest();rows=json.loads(raw)['data']['dividends']['rows'];events=[]
 for row in rows:
  iso=lambda s:datetime.strptime(s,'%m/%d/%Y').date().isoformat()
  if row['exOrEffDate']=='N/A':continue
  ex=iso(row['exOrEffDate'])
  if '2021-01-01'<=ex<='2026-07-30':events.append(dict(ex_date=ex,payment_date=iso(row['paymentDate']),amount=str(F(row['amount'].replace('$',''))),currency=row['currency'],type=row['type']))
 assert len(events)==len({e['ex_date'] for e in events})
 results={};matched=[]
 for window,(folder,anchor,end,count) in WINDOWS.items():
  days=read(ROOT/'tmp'/folder/'execution_inputs.json')['assembled']['session_dates'];assert days[0]==anchor and days[-1]==end and len(days)==count+1
  relevant=[e for e in events if days[1]<=e['ex_date']<=end];assert {e['ex_date'] for e in relevant}=={d for d in provider_events if days[1]<=d<=end}
  for e in relevant:
   assert e['currency']=='USD' and F(e['amount'])>0 and e['payment_date']>=e['ex_date'];assert abs(F(e['amount'])-provider_events[e['ex_date']])<=F(1,1000)
   matched.append(dict(**e,provider_amount=str(provider_events[e['ex_date']])))
  book=run_book(days,panel,relevant);(out/(window+'.book.json')).write_text(json.dumps(book,indent=2));results[window]=summarize(book,anchor=anchor,expected_sessions=days[1:])
 report=dict(results=results,source_hashes=pins,event_matches=matched,rules=['Gross exact Nasdaq exchange cash amounts; provider ex-date set must agree, amount difference <=.001 allowed as rounding and retained.','Initial20k, no external flows/leverage, integer shares; buy price opening*1.0005, commission0.','Ex-date opening holdings establish entitlement; issuer pay date posts at first available session close; reinvest only following session open.','Every open invests all spendable cash including residual; no terminal liquidation.','Payment date is exchange data, not actual HSBC receipt; no tax withholding. No future dividend used to select investments.'],source_url='https://api.nasdaq.com/api/quote/QQQ/dividends?assetclass=etf',observed_at=datetime.now(timezone.utc).isoformat())
 (out/'report.json').write_text(json.dumps(report,indent=2));print({k:(r['cagr'],r['daily_close_maximum_drawdown'],r['fill_count']) for k,r in results.items()})
if __name__=='__main__':run()
