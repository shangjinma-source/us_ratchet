"""Offline exact decoder for the one frozen AAPL 2022 quote-minute probe; no download."""
import json,hashlib
from decimal import Decimal
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
def run():
 out=ROOT/'tmp/dukascopy_minute_probe_20261105';raw=(out/'aapl_20220103_bid.response').read_bytes();receipt=json.loads((out/'receipt.json').read_bytes());assert receipt['status']==200 and receipt['request_count']==1 and hashlib.sha256(raw).hexdigest()==receipt['sha256']
 x=json.loads(raw,parse_float=Decimal);assert x['shift']==60000 and all(len(x[k])==len(x['times']) for k in ['opens','highs','lows','closes','volumes']);t=x['timestamp'];units={k:int(x[k]/x['multiplier']) for k in ['open','high','low','close']};rows=[]
 for i,dt in enumerate(x['times']):
  assert type(dt) is int and dt>=0;t+=dt*x['shift'];prices={}
  for k in units:units[k]+=x[k+'s'][i];prices[k]=units[k]*x['multiplier']
  assert prices['low']<=min(prices['open'],prices['close'])<=max(prices['open'],prices['close'])<=prices['high']
  utc=datetime.fromtimestamp(t/1000,timezone.utc);et=utc.astimezone(ZoneInfo('America/New_York'));rows.append(dict(utc=utc.isoformat(),et=et.isoformat(),**{k:str(v) for k,v in prices.items()},provider_quote_volume_raw=str(x['volumes'][i])))
 assert len({r['utc'] for r in rows})==len(rows)
 info=dict(actual_rows=len(rows),first=rows[0],last=rows[-1],regular_session_rows=sum('09:30:00'<=r['et'][11:19]<'16:00:00' for r in rows),premarket_rows=sum('04:00:00'<=r['et'][11:19]<'09:30:00' for r in rows),postmarket_rows=sum('16:00:00'<=r['et'][11:19]<'20:00:00' for r in rows),positive_provider_quote_volume_rows=sum(Decimal(r['provider_quote_volume_raw'])>0 for r in rows),calendar_gaps=[(rows[i-1]['utc'],rows[i]['utc']) for i in range(1,len(rows)) if datetime.fromisoformat(rows[i]['utc'])-datetime.fromisoformat(rows[i-1]['utc'])!=timedelta(minutes=1)],ohlc_valid=True,padding_inserted=False,trade_volume_verified=False,price_side='BID',source_sha256=receipt['sha256'],decoder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (out/'decoded_actual_rows.json').write_text(json.dumps(rows,indent=2));(out/'checks.json').write_text(json.dumps(info,indent=2));print(json.dumps(info))
if __name__=='__main__':run()
