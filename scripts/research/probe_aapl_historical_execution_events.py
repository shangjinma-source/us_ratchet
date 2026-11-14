"""Bounded AAPL event execution comparison; no account writes or strategy promotion."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from scripts.research.roa_entry_timing_event_probe import money


def inspect(raw, event):
    data = json.loads(raw)
    opening = int(datetime.fromisoformat(event['date'] + 'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp())
    if data.get('s') != 'ok' or data.get('t') != list(range(opening, opening + 390 * 60, 60)):
        raise ValueError('INCOMPLETE_OR_WRONG_SESSION')
    if any(len(data[k]) != 390 for k in ('o', 'h', 'l', 'c', 'v')):
        raise ValueError('COLUMN_LENGTH_MISMATCH')
    for i in range(390):
        o,h,l,c,v = [data[k][i] for k in ('o','h','l','c','v')]
        if not all(math.isfinite(x) for x in (o,h,l,c,v)) or not 0 < l <= min(o,c) <= max(o,c) <= h or v < 0:
            raise ValueError('INVALID_BAR')
    ref = data['o'][0]
    arms = []
    policies = [('OPEN_REFERENCE',1,1),('1030',60,1),('1200',150,1)]
    if event['side']=='BUY': policies.append(('OPEN_MINUS_1PCT',1,.99))
    for name,start,multiplier in policies:
        limit = money((ref if start==1 else data['c'][start-1])*multiplier)
        filled = None
        for i in range(start,385):
            crossed = data['l'][i] < limit if event['side']=='BUY' else data['h'][i] > limit
            if crossed and data['v'][i]>0:
                price = min(data['o'][i],limit) if event['side']=='BUY' else max(data['o'][i],limit)
                improvement = (ref-price)/ref if event['side']=='BUY' else (price-ref)/ref
                filled = dict(minute=i,price=price,improvement_pct=100*improvement)
                break
        arms.append(dict(name=name,limit=limit,fill=filled))
    return dict(status='COMPLETE_PRICE_EXECUTION_PROXY',reference=ref,arms=arms)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    raw=args.manifest.read_bytes()
    events=[e for e in json.loads(raw)['records'] if e['security_id']=='research:security:aapl' and e['phase']=='OPEN']
    args.directory.mkdir(parents=True,exist_ok=True)
    contract=dict(manifest_sha256=sha256(raw).hexdigest(),events=events,max_requests=len(events),retries=0,
        assumptions=['Single security, strictly crossing hypothetical limits, no queue or partial-fill model.',
        'Every event independent; not a cash-constrained account replay or annual performance.',
        'No use of future low to choose entry; unmatched orders expire at 15:55.',
        'Timezone America/New_York; no missing-minute padding.'])
    (args.directory/'contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
    def run(event):
        result=dict(event=event)
        try:
            path=args.directory/(event['date']+'.json')
            url='https://api.marketdata.app/v1/stocks/candles/1/AAPL?from='+event['date']+'&to='+event['date']
            result['url']=url
            if not path.exists():
                with urlopen(url,timeout=15) as response:
                    body=response.read(2000000)
                    result['http_status']=response.status
                path.write_bytes(body)
            body=path.read_bytes()
            result['sha256']=sha256(body).hexdigest()
            result.update(inspect(body,event))
        except Exception as error: result.update(status='EXCLUDED',error=str(error))
        return result
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,events))
    (args.directory/'event_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps([dict(date=r['event']['date'],side=r['event']['side'],status=r['status']) for r in results]))


if __name__=='__main__':main()
