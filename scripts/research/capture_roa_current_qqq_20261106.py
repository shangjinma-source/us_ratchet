"""One bounded raw QQQ capture, then compare to saved cache; never trade."""
import csv
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.current_research_close_capture import default_fetch
from scripts.research.screen_profitability_roa_continuous_20261106 import market_states

ROOT=Path(__file__).resolve().parents[2]


def main():
    directory=ROOT/'tmp/roa_current_qqq_raw_20261106'
    directory.mkdir(exist_ok=False)
    started=datetime.now(timezone.utc)
    start=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp())
    end=int(datetime(2026,11,6,tzinfo=timezone.utc).timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/QQQ?period1={start}&period2={end}&interval=1d&events=div,splits,capitalGains'
    receipt=dict(url=url,started_at=started.isoformat(),maximum_calls=1,production_activated=False)
    (directory/'intent.json').write_text(json.dumps(receipt,indent=2))
    fetched=default_fetch(url,timeout=15,max_bytes=8000000)
    raw=fetched['raw'];(directory/'QQQ.response.bin').write_bytes(raw)
    receipt.update(http_status=fetched['http_status'],final_url=fetched['final_url'],
        received_at=datetime.now(timezone.utc).isoformat(),sha256=sha256(raw).hexdigest(),bytes=len(raw))
    (directory/'receipt.json').write_text(json.dumps(receipt,indent=2))
    assert fetched['http_status']==200 and fetched['final_url']==url and len(raw)<=8000000
    document=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    assert document['chart']['error'] is None
    chart=document['chart']['result'][0]
    assert chart['meta']['symbol']=='QQQ' and chart['meta']['currency']=='USD'
    assert chart['meta']['exchangeTimezoneName']=='America/New_York'
    dates=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in chart['timestamp']]
    values=chart['indicators']['quote'][0]['close']
    assert dates==sorted(set(dates)) and dates[-1]=='2026-11-05'
    assert len(dates)==len(values) and all(type(v) in (float,int) and v>0 for v in values)
    prices=dict(zip(dates,values));states=market_states(prices,'SMA200')
    snapshot=ROOT/'tmp/roa_november_qqq_20261106.csv';saved=snapshot.read_bytes()
    cache={r['Date']:float(r['Close']) for r in csv.DictReader(io.StringIO(saved.decode('utf-8-sig')))}
    overlap=[d for d in dates if d in cache]
    differences=[dict(date=d,raw_close=prices[d],cache_close=cache[d]) for d in overlap if abs(prices[d]-cache[d])>0.0051]
    output=dict(status='RAW_CAPTURE_CACHE_COMPARISON',last_date=dates[-1],raw_risk_on=states[dates[-1]],
        rows=len(dates),overlap_rows=len(overlap),differences_over_cent_rounding=differences,
        source_sha256=receipt['sha256'],cache_sha256=sha256(saved).hexdigest(),
        source_url=url,production_activated=False,orders_created=False,
        limitation='Same provider repeat capture, not independent vendor confirmation. No exchange-calendar or all-action certification.')
    (directory/'comparison.json').write_text(json.dumps(output,indent=2))
    print(json.dumps({k:v for k,v in output.items() if k!='differences_over_cent_rounding'}))
    print('differences',len(differences))


if __name__=='__main__':main()
